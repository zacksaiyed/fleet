// fleet/fleet/page/support_dashboard_chat/support_dashboard_chat.js
// WhatsApp-style chat page — auto-selects technician passed from grid dashboard

frappe.provide('fleet.support_dashboard_chat');

frappe.pages['support-dashboard-chat'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Support Dashboard',
		single_column: true,
	});
	fleet.support_dashboard_chat.init(wrapper);
};

frappe.pages['support-dashboard-chat'].on_page_show = function (wrapper) {
	if (!fleet.support_dashboard_chat.instance) return;

	const instance = fleet.support_dashboard_chat.instance;
	const opts = frappe.route_options || {};
	const preselect = opts.technician || null;

	// Always reload cards, then auto-select if technician passed
	instance._load_technicians_then(function () {
		if (preselect) {
			const tech = instance.technicians.find(t => t.name === preselect);
			if (tech) instance._select_technician(tech);
			frappe.route_options = {};
		}
	});
};

fleet.support_dashboard_chat.init = function (wrapper) {
	fleet.support_dashboard_chat.instance = new SupportDashboardChat(wrapper);
};

//  MAIN CLASS
class SupportDashboardChat {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.$main = $(wrapper).find('.page-content');

		this.technicians    = [];
		this.selected_tech  = null;
		this.selected_job   = null;
		this.jobs           = [];
		this.realtime_bound = false;

		this._inject_styles();
		this._render_shell();
		this._load_technicians_then();
		this._bind_realtime();
	}

	// Shell
	_render_shell() {
		this.$main.html(`
			<div class="sd-root">

				<!-- TOP BAR: Technician Cards -->
				<div class="sd-topbar">
					<div class="sd-topbar-label">TECHNICIANS</div>
					<div class="sd-tech-list" id="sd-tech-list">
						<div class="sd-loading-dots">
							<span></span><span></span><span></span>
						</div>
					</div>
				</div>

				<!-- BODY -->
				<div class="sd-body">

					<!-- LEFT: Job List -->
					<div class="sd-jobs-panel" id="sd-jobs-panel">
						<div class="sd-jobs-header">
							<span id="sd-jobs-title">Select a technician</span>
							<span class="sd-jobs-count" id="sd-jobs-count"></span>
						</div>
						<div class="sd-jobs-list" id="sd-jobs-list">
							<div class="sd-empty-state">
								<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
									<rect x="2" y="3" width="20" height="14" rx="2"/>
									<line x1="8" y1="21" x2="16" y2="21"/>
									<line x1="12" y1="17" x2="12" y2="21"/>
								</svg>
								<p>Select a technician to view jobs</p>
							</div>
						</div>
					</div>

					<!-- RIGHT: Chat Panel -->
					<div class="sd-chat-panel" id="sd-chat-panel">
						<div class="sd-chat-empty">
							<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
								<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
							</svg>
							<h3>Select a job to start chatting</h3>
							<p>Messages will appear here</p>
						</div>
					</div>

				</div>
			</div>
		`);
	}

	// Load Technician
	_load_technicians_then(callback) {
		frappe.call({
			method: 'fleet.api.dashboard_chat.get_all_technicians_summary',
			callback: (r) => {
				this.technicians = r.message || [];
				this._render_tech_cards();
				if (typeof callback === 'function') callback();
			},
		});
	}

	_render_tech_cards() {
		const $list = $('#sd-tech-list');
		$list.empty();

		if (!this.technicians.length) {
			$list.html('<div class="sd-no-tech">No technicians found</div>');
			return;
		}

		const COLORS = [
			'#2490ef','#7b5ea7','#e67e22','#27ae60','#e74c3c','#16a085',
			'#d35400','#2980b9','#8e44ad','#c0392b','#1abc9c','#f39c12',
			'#2ecc71','#3498db','#9b59b6','#e91e63'
		];
		
		this.technicians.forEach((tech, idx) => {
			const color = COLORS[idx % COLORS.length];
			const initials = (tech.full_name || tech.name)
				.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

			const avatar = tech.user_image
				? `<img src="${tech.user_image}" class="sd-tech-avatar-img" alt="${initials}">`
				: `<div class="sd-tech-avatar-initials" style="background:linear-gradient(135deg,${color}dd,${color}88)">${initials}</div>`;

			const unread    = parseInt(tech.total_unread || 0);
			const pending   = parseInt(tech.pending      || 0);
			const completed = parseInt(tech.completed    || 0);

			const badge = `<span class="sd-tech-unread ${unread ? '' : 'sd-hidden'}" data-tech="${tech.name}">${unread}</span>`;

			const $card = $(`
				<div class="sd-tech-card" data-tech="${tech.name}">
					${badge}
					<div class="sd-tech-avatar">${avatar}</div>
					<div class="sd-tech-info">
						<div class="sd-tech-name">${tech.full_name || tech.name}</div>
						<div class="sd-tech-stats">
							<span class="stat-pill pending">${pending} Pending</span>
							<span class="stat-pill done">${completed} Completed</span>
						</div>
					</div>
				</div>
			`);

			$card.on('click', () => this._select_technician(tech));
			$list.append($card);
		});

		// Re-highlight active card if one is already selected
		if (this.selected_tech) {
			$(`.sd-tech-card[data-tech="${this.selected_tech.name}"]`).addClass('active');
		}
	}

	// Select Technician
	_select_technician(tech) {
		this.selected_tech = tech;
		this.selected_job  = null;

		$('.sd-tech-card').removeClass('active');
		$(`.sd-tech-card[data-tech="${tech.name}"]`).addClass('active');

		// Scroll selected card into view
		const $card = $(`.sd-tech-card[data-tech="${tech.name}"]`);
		if ($card.length) {
			$card[0].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
		}

		$('#sd-chat-panel').html(`
			<div class="sd-chat-empty">
				<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
					<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
				</svg>
				<h3>Select a job to start chatting</h3>
				<p>Messages will appear here</p>
			</div>
		`);

		$('#sd-jobs-title').text(tech.full_name || tech.name);
		$('#sd-jobs-list').html(`
			<div class="sd-loading-dots center">
				<span></span><span></span><span></span>
			</div>
		`);

		this._load_jobs(tech.name);
	}

	// Load Jobs
	_load_jobs(technician) {
		frappe.call({
			method: 'fleet.api.dashboard_chat.get_technician_jobs',
			args: { technician },
			callback: (r) => {
				this.jobs = r.message || [];
				$('#sd-jobs-count').text(
					`${this.jobs.length} job${this.jobs.length !== 1 ? 's' : ''}`
				);
				this._render_jobs();
			},
		});
	}

	_render_jobs() {
		const $list = $('#sd-jobs-list');
		$list.empty();

		if (!this.jobs.length) {
			$list.html(`
				<div class="sd-empty-state">
					<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
						<circle cx="12" cy="12" r="10"/>
						<line x1="12" y1="8" x2="12" y2="12"/>
						<line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
					<p>No jobs assigned</p>
				</div>
			`);
			return;
		}

		const STATUS_COLORS = {
			'Pending':     '#94a3b8',
			'In Progress': '#3b82f6',
			'Hold':        '#f59e0b',
			'Completed':   '#22c55e',
			'Cancelled':   '#ef4444',
		};

		this.jobs.forEach((job) => {
			const unread    = parseInt(job.unread_count_support || 0);
			const dot_color = STATUS_COLORS[job.status] || '#94a3b8';

			const $item = $(`
				<div class="sd-job-item" data-job="${job.name}">
					<div class="sd-job-status-dot" style="background:${dot_color}"></div>
					<div class="sd-job-content">
						<div class="sd-job-top">
							<span class="sd-job-title">${job.title || job.name}</span>
							<span class="sd-job-time">${frappe.datetime.prettyDate(job.modified)}</span>
						</div>
						<div class="sd-job-bottom">
							<span class="sd-job-meta">${job.task_subject || job.task}</span>
							${job.vehicle_number ? `<span class="sd-job-vehicle">🚗 ${job.vehicle_number}</span>` : ''}
						</div>
						<div class="sd-job-footer">
							<span class="sd-job-status-tag" style="color:${dot_color}">${job.status}</span>
							${job.task_type && job.task_type !== 'None'
								? `<span class="sd-job-action">${job.task_type}</span>`
								: ''}
						</div>
					</div>
					<div class="sd-job-unread ${unread ? '' : 'sd-hidden'}" data-job-unread="${job.name}">${unread}</div>
				</div>
			`);

			$item.on('click', () => this._select_job(job));
			$list.append($item);
		});
	}

	// Select Job
	_select_job(job) {
		this.selected_job = job;

		$('.sd-job-item').removeClass('active');
		$(`.sd-job-item[data-job="${job.name}"]`).addClass('active');

		$(`.sd-job-unread[data-job-unread="${job.name}"]`).text('0').addClass('sd-hidden');
		job.unread_count_support = 0;

		frappe.call({
			method: 'fleet.api.dashboard_chat.mark_messages_read',
			args: { job: job.name, reader_role: 'Support' },
		});

		this._render_chat_panel(job);
		this._load_messages(job.name);
	}

	// Chat Panel
	_render_chat_panel(job) {
		const STATUS_COLORS = {
			'Pending':     '#94a3b8',
			'In Progress': '#3b82f6',
			'Hold':        '#f59e0b',
			'Completed':   '#22c55e',
			'Cancelled':   '#ef4444',
		};
		const dot = STATUS_COLORS[job.status] || '#94a3b8';

		$('#sd-chat-panel').html(`
			<div class="sd-chat-wrapper">

				<div class="sd-chat-header">
					<div class="sd-chat-header-left">
						<div class="sd-chat-job-title">${job.title || job.name}</div>
						<div class="sd-chat-job-meta">
							<span class="sd-chat-status-dot" style="background:${dot}"></span>
							<span style="color:${dot};font-weight:600">${job.status}</span>
							<span class="sd-meta-sep">·</span>
							<span>${job.task_subject || job.task}</span>
							${job.vehicle_number
								? `<span class="sd-meta-sep">·</span><span>🚗 ${job.vehicle_number}</span>`
								: ''}
							${job.task_type && job.task_type !== 'None'
								? `<span class="sd-meta-sep">·</span><span>${job.task_type}</span>`
								: ''}
						</div>
					</div>
					<div class="sd-chat-header-right">
						<button class="sd-open-job-btn" onclick="frappe.set_route('Form','Job','${job.name}')">
							Open Job ↗
						</button>
					</div>
				</div>

				<div class="sd-messages-wrap" id="sd-messages-wrap">
					<div class="sd-messages-list" id="sd-messages-list">
						<div class="sd-msgs-loading">
							<div class="sd-loading-dots center">
								<span></span><span></span><span></span>
							</div>
						</div>
					</div>
				</div>

				<div class="sd-chat-input-wrap">
					<textarea
						id="sd-chat-input"
						class="sd-chat-input"
						placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
						rows="1"
					></textarea>
					<button class="sd-send-btn" id="sd-send-btn">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
							<line x1="22" y1="2" x2="11" y2="13"/>
							<polygon points="22 2 15 22 11 13 2 9 22 2"/>
						</svg>
					</button>
				</div>

			</div>
		`);

		$('#sd-chat-input')
			.on('keydown', (e) => {
				if (e.key === 'Enter' && !e.shiftKey) {
					e.preventDefault();
					this._send_message();
				}
			})
			.on('input', function () {
				this.style.height = '44px';
				this.style.height = Math.min(this.scrollHeight, 120) + 'px';
			});

		$('#sd-send-btn').on('click', () => this._send_message());
	}

	// Load Messages
	_load_messages(job_name) {
		frappe.call({
			method: 'fleet.api.dashboard_chat.get_job_chat_messages',
			args: { job: job_name },
			callback: (r) => {
				const msgs  = r.message || [];
				const $list = $('#sd-messages-list');
				$list.empty();

				if (!msgs.length) {
					$list.html('<div class="sd-msgs-empty">No messages yet. Start the conversation.</div>');
					return;
				}

				msgs.forEach(msg => this._append_bubble(msg));
				this._scroll_to_bottom();
			},
		});
	}

	// Send Message
	_send_message() {
		if (!this.selected_job) return;

		const $input  = $('#sd-chat-input');
		const message = $input.val().trim();
		if (!message) return;

		const $btn = $('#sd-send-btn');
		$btn.prop('disabled', true);
		$input.val('').css('height', '44px');

		const job = this.selected_job;

		frappe.call({
			method: 'fleet.api.dashboard_chat.publish_job_chat',
			args: {
				cdn:         job.task_job_row || job.name,
				message:     message,
				sender_name: frappe.session.user_fullname || frappe.session.user,
				role:        'Support',
				job:         job.name,
			},
			callback: (r) => {
				$btn.prop('disabled', false);
				if (!r.exc) {
					this._append_bubble({
						sender:      frappe.session.user,
						sender_name: frappe.session.user_fullname || frappe.session.user,
						sender_role: 'Support',
						message:     message,
						content:     message,
						sent_by:     frappe.session.user,
						role:        'Support',
						creation:    frappe.datetime.now_datetime(),
					});
					this._scroll_to_bottom();
				}
			},
		});
	}

	// Append Bubble
	_append_bubble(msg) {
		const $list = $('#sd-messages-list');
		$list.find('.sd-msgs-empty, .sd-msgs-loading').remove();

		const is_mine = (msg.sender || msg.sent_by) === frappe.session.user;
		const role    = msg.sender_role || msg.role || 'Support';
		const name    = msg.sender_name || msg.sender || '?';
		const content = msg.message    || msg.content || '';

		const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
		const time     = msg.creation
			? frappe.datetime.str_to_user(msg.creation, true)
			: 'Just now';

		const avatar_color = role === 'Technician' ? '#3b82f6' : '#10b981';

		$list.append(`
			<div class="sd-bubble-row ${is_mine ? 'mine' : 'theirs'}">
				${!is_mine
					? `<div class="sd-bubble-avatar" style="background:${avatar_color}">${initials}</div>`
					: ''}
				<div class="sd-bubble-wrap">
					${!is_mine ? `<div class="sd-bubble-name">${frappe.utils.escape_html(name)}</div>` : ''}
					<div class="sd-bubble ${is_mine ? 'sd-bubble-mine' : 'sd-bubble-theirs'}">
						${frappe.utils.escape_html(content)}
					</div>
					<div class="sd-bubble-time ${is_mine ? 'sd-time-right' : ''}">${time}</div>
				</div>
				${is_mine
					? `<div class="sd-bubble-avatar" style="background:${avatar_color}">${initials}</div>`
					: ''}
			</div>
		`);
	}

	_scroll_to_bottom() {
		const $wrap = $('#sd-messages-wrap');
		if ($wrap.length) $wrap.scrollTop($wrap[0].scrollHeight);
	}

	// Realtime
	_bind_realtime() {
		if (this.realtime_bound) return;
		this.realtime_bound = true;

		frappe.realtime.on('support_dashboard_new_message', (data) => {
			// Active job is open — append bubble directly
			if (this.selected_job && data.job === this.selected_job.name) {
				if (data.sent_by !== frappe.session.user) {
					this._append_bubble(data);
					this._scroll_to_bottom();
					frappe.call({
						method: 'fleet.api.dashboard_chat.mark_messages_read',
						args: { job: data.job, reader_role: 'Support' },
					});
				}
			} else {
				// Different job — increment unread badge on job row
				const $badge = $(`.sd-job-unread[data-job-unread="${data.job}"]`);
				if ($badge.length) {
					$badge.text((parseInt($badge.text()) || 0) + 1).removeClass('sd-hidden');
				}

				// Update technician card unread total
				const tech_name = data.sent_by || (this.selected_tech && this.selected_tech.name);
				if (tech_name) this._refresh_tech_badge(tech_name);

				frappe.show_alert({
					message: `💬 ${data.sender_name || data.sent_by}: ${(data.content || '').slice(0, 60)}`,
					indicator: 'blue',
				}, 5);
			}
		});

		frappe.realtime.on('support_dashboard_read', (data) => {
			$(`.sd-job-unread[data-job-unread="${data.job}"]`).text('0').addClass('sd-hidden');
		});
	}

	_refresh_tech_badge(tech_name) {
		frappe.db.get_list('Job', {
			filters: { assigned_technician: tech_name },
			fields:  ['unread_count_support'],
		}).then((rows) => {
			const total  = (rows || []).reduce((s, r) => s + (parseInt(r.unread_count_support) || 0), 0);
			const $badge = $(`.sd-tech-unread[data-tech="${tech_name}"]`);
			$badge.text(total);
			total > 0 ? $badge.removeClass('sd-hidden') : $badge.addClass('sd-hidden');
		});
	}

	// Styles
	_inject_styles() {
		if ($('#sd-chat-styles').length) return;

		$(`<style id="sd-chat-styles">

		/* ROOT */
		.sd-root {
			display: flex;
			flex-direction: column;
			height: calc(100vh - 120px);
			background: var(--bg-color);
			border-radius: 8px;
			overflow: hidden;
			border: 1px solid var(--border-color);
		}

		/* TOP BAR */
		.sd-topbar {
			display: flex;
			align-items: center;
			gap: 16px;
			padding: 12px 20px;
			background: var(--fg-color);
			border-bottom: 1px solid var(--border-color);
			flex-shrink: 0;
			min-height: 90px;
			box-sizing: border-box;
		}
		.sd-topbar-label {
			font-size: 10px;
			font-weight: 700;
			color: var(--text-muted);
			letter-spacing: 0.1em;
			white-space: nowrap;
		}
		.sd-tech-list {
			display: flex;
			gap: 10px;
			flex: 1;
			overflow-x: auto;
			overflow-y: visible;
			padding: 4px 2px 6px 2px;
			align-items: stretch;
		}
		.sd-tech-list::-webkit-scrollbar { height: 4px; }
		.sd-tech-list::-webkit-scrollbar-thumb {
			background: var(--border-color);
			border-radius: 2px;
		}

		/* TECH CARD */
		.sd-tech-card {
			position: relative;
			display: flex;
			flex-direction: row;
			align-items: center;
			gap: 10px;
			padding: 10px 14px;
			background: var(--control-bg);
			border: 1.5px solid var(--border-color);
			border-radius: 10px;
			cursor: pointer;
			flex-shrink: 0;
			width: 220px;
			min-height: 64px;
			box-sizing: border-box;
			transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
			overflow: visible;
		}
		.sd-tech-card:hover {
			border-color: var(--primary);
			background: var(--blue-50);
		}
		.sd-tech-card.active {
			border-color: var(--primary);
			background: var(--blue-50);
			box-shadow: 0 0 0 3px var(--blue-100);
		}

		/* Avatar */
		.sd-tech-avatar {
			flex-shrink: 0;
			width: 40px;
			height: 40px;
			border-radius: 50%;
			overflow: hidden;
		}
		.sd-tech-avatar-img {
			width: 100%;
			height: 100%;
			object-fit: cover;
			border-radius: 50%;
		}
		.sd-tech-avatar-initials {
			width: 40px;
			height: 40px;
			border-radius: 50%;
			color: white;
			font-size: 14px;
			font-weight: 700;
			display: flex;
			align-items: center;
			justify-content: center;
		}

		/* Info */
		.sd-tech-info {
			flex: 1;
			min-width: 0;
			display: flex;
			flex-direction: column;
			gap: 5px;
		}
		.sd-tech-name {
			font-size: 13px;
			font-weight: 600;
			color: var(--text-color);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			line-height: 1.2;
		}

		/* Pills — fixed row, no wrap */
		.sd-tech-stats {
			display: flex;
			flex-direction: row;
			flex-wrap: nowrap;
			gap: 4px;
			align-items: center;
		}
		.stat-pill {
			display: inline-flex;
			align-items: center;
			font-size: 10px;
			font-weight: 600;
			padding: 2px 7px;
			border-radius: 10px;
			white-space: nowrap;
			line-height: 1.4;
			flex-shrink: 0;
		}
		.stat-pill.pending  { background: #f1f5f9; color: #475569; }
		.stat-pill.done     { background: #dcfce7; color: #15803d; }

		/* Unread badge */
		.sd-tech-unread {
			position: absolute;
			top: -6px;
			right: -6px;
			background: #ef4444;
			color: white;
			font-size: 10px;
			font-weight: 700;
			min-width: 18px;
			height: 18px;
			border-radius: 9px;
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 0 4px;
			box-shadow: 0 0 0 2px var(--fg-color);
			z-index: 1;
		}
		.sd-hidden { display: none !important; }

		/* BODY */
		.sd-body {
			display: flex;
			flex: 1;
			overflow: hidden;
		}

		/* JOBS PANEL */
		.sd-jobs-panel {
			width: 320px;
			flex-shrink: 0;
			display: flex;
			flex-direction: column;
			border-right: 1px solid var(--border-color);
			background: var(--fg-color);
		}
		.sd-jobs-header {
			padding: 12px 16px;
			border-bottom: 1px solid var(--border-color);
			display: flex;
			align-items: center;
			justify-content: space-between;
			font-weight: 600;
			font-size: 13px;
			color: var(--text-color);
			flex-shrink: 0;
		}
		.sd-jobs-count {
			font-size: 11px;
			color: var(--text-muted);
			font-weight: 400;
		}
		.sd-jobs-list {
			flex: 1;
			overflow-y: auto;
		}
		.sd-jobs-list::-webkit-scrollbar { width: 3px; }
		.sd-jobs-list::-webkit-scrollbar-thumb {
			background: var(--border-color);
			border-radius: 2px;
		}

		/* JOB ITEM */
		.sd-job-item {
			display: flex;
			align-items: flex-start;
			gap: 10px;
			padding: 12px 16px;
			cursor: pointer;
			border-bottom: 1px solid var(--border-color);
			transition: background 0.1s;
			position: relative;
		}
		.sd-job-item:hover  { background: var(--blue-50); }
		.sd-job-item.active {
			background: var(--blue-50);
			border-left: 3px solid var(--primary);
		}
		.sd-job-status-dot {
			width: 8px;
			height: 8px;
			border-radius: 50%;
			flex-shrink: 0;
			margin-top: 4px;
		}
		.sd-job-content   { flex: 1; min-width: 0; }
		.sd-job-top {
			display: flex;
			justify-content: space-between;
			align-items: flex-start;
			gap: 4px;
		}
		.sd-job-title {
			font-size: 13px;
			font-weight: 600;
			color: var(--text-color);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			max-width: 160px;
		}
		.sd-job-time   { font-size: 10px; color: var(--text-muted); white-space: nowrap; }
		.sd-job-bottom {
			display: flex;
			gap: 6px;
			align-items: center;
			margin-top: 2px;
			flex-wrap: wrap;
		}
		.sd-job-meta    { font-size: 11px; color: var(--text-muted); }
		.sd-job-vehicle { font-size: 11px; color: var(--text-muted); }
		.sd-job-footer  {
			display: flex;
			gap: 6px;
			margin-top: 4px;
			align-items: center;
		}
		.sd-job-status-tag { font-size: 10px; font-weight: 600; }
		.sd-job-action {
			font-size: 10px;
			background: var(--blue-100);
			color: var(--blue-600);
			padding: 1px 6px;
			border-radius: 4px;
		}
		.sd-job-unread {
			background: #ef4444;
			color: white;
			font-size: 10px;
			font-weight: 700;
			min-width: 18px;
			height: 18px;
			border-radius: 9px;
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 0 4px;
			flex-shrink: 0;
		}

		/* CHAT PANEL */
		.sd-chat-panel {
			flex: 1;
			display: flex;
			flex-direction: column;
			background: var(--bg-color);
			overflow: hidden;
		}
		.sd-chat-empty {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			height: 100%;
			gap: 12px;
			color: var(--text-muted);
		}
		.sd-chat-empty h3 {
			font-size: 16px;
			font-weight: 600;
			color: var(--text-color);
			margin: 0;
		}
		.sd-chat-empty p  { font-size: 13px; margin: 0; }
		.sd-chat-wrapper  { display: flex; flex-direction: column; height: 100%; }

		/* Chat header */
		.sd-chat-header {
			padding: 12px 20px;
			background: var(--fg-color);
			border-bottom: 1px solid var(--border-color);
			display: flex;
			align-items: center;
			justify-content: space-between;
			flex-shrink: 0;
		}
		.sd-chat-job-title {
			font-size: 15px;
			font-weight: 700;
			color: var(--text-color);
		}
		.sd-chat-job-meta {
			display: flex;
			align-items: center;
			gap: 6px;
			font-size: 12px;
			color: var(--text-muted);
			margin-top: 3px;
			flex-wrap: wrap;
		}
		.sd-chat-status-dot {
			width: 7px;
			height: 7px;
			border-radius: 50%;
			flex-shrink: 0;
		}
		.sd-meta-sep { color: var(--border-color); }
		.sd-open-job-btn {
			font-size: 12px;
			font-weight: 600;
			padding: 5px 12px;
			border-radius: 6px;
			border: 1px solid var(--border-color);
			background: var(--control-bg);
			color: var(--text-color);
			cursor: pointer;
			transition: all 0.15s;
			white-space: nowrap;
		}
		.sd-open-job-btn:hover {
			border-color: var(--primary);
			color: var(--primary);
		}

		/* Messages */
		.sd-messages-wrap {
			flex: 1;
			overflow-y: auto;
			padding: 16px 20px;
		}
		.sd-messages-wrap::-webkit-scrollbar { width: 4px; }
		.sd-messages-wrap::-webkit-scrollbar-thumb {
			background: var(--border-color);
			border-radius: 2px;
		}
		.sd-messages-list {
			display: flex;
			flex-direction: column;
			gap: 12px;
		}
		.sd-msgs-empty,
		.sd-msgs-loading {
			text-align: center;
			color: var(--text-muted);
			font-size: 13px;
			padding: 40px 0;
		}

		/* Bubbles */
		.sd-bubble-row {
			display: flex;
			align-items: flex-end;
			gap: 8px;
		}
		.sd-bubble-row.mine   { flex-direction: row-reverse; }
		.sd-bubble-row.theirs { flex-direction: row; }
		.sd-bubble-avatar {
			width: 28px;
			height: 28px;
			border-radius: 50%;
			color: white;
			font-size: 10px;
			font-weight: 700;
			display: flex;
			align-items: center;
			justify-content: center;
			flex-shrink: 0;
		}
		.sd-bubble-wrap {
			display: flex;
			flex-direction: column;
			max-width: 65%;
		}
		.sd-bubble-name {
			font-size: 11px;
			color: var(--text-muted);
			margin-bottom: 3px;
			font-weight: 600;
		}
		.sd-bubble {
			padding: 9px 13px;
			font-size: 13px;
			line-height: 1.5;
			word-break: break-word;
			box-shadow: 0 1px 2px rgba(0,0,0,0.06);
		}
		.sd-bubble-mine {
			background: var(--primary);
			color: white;
			border-radius: 14px 14px 2px 14px;
		}
		.sd-bubble-theirs {
			background: var(--fg-color);
			color: var(--text-color);
			border: 1px solid var(--border-color);
			border-radius: 14px 14px 14px 2px;
		}
		.sd-bubble-time {
			font-size: 10px;
			color: var(--text-muted);
			margin-top: 3px;
		}
		.sd-time-right { text-align: right; }

		/* Input */
		.sd-chat-input-wrap {
			padding: 12px 16px;
			background: var(--fg-color);
			border-top: 1px solid var(--border-color);
			display: flex;
			gap: 10px;
			align-items: flex-end;
			flex-shrink: 0;
		}
		.sd-chat-input {
			flex: 1;
			resize: none;
			min-height: 44px;
			max-height: 120px;
			border: 1px solid var(--border-color);
			border-radius: 22px;
			padding: 10px 16px;
			font-size: 13px;
			font-family: var(--font-stack);
			background: var(--control-bg);
			color: var(--text-color);
			outline: none;
			transition: border-color 0.15s;
			line-height: 1.4;
		}
		.sd-chat-input:focus { border-color: var(--primary); }
		.sd-send-btn {
			width: 44px;
			height: 44px;
			border-radius: 50%;
			background: var(--primary);
			color: white;
			border: none;
			cursor: pointer;
			display: flex;
			align-items: center;
			justify-content: center;
			flex-shrink: 0;
			transition: all 0.15s;
		}
		.sd-send-btn:hover    { filter: brightness(1.1); transform: scale(1.05); }
		.sd-send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

		/* SHARED STATES */
		.sd-empty-state {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			padding: 48px 24px;
			gap: 12px;
			color: var(--text-muted);
			text-align: center;
		}
		.sd-empty-state p { font-size: 13px; margin: 0; }
		.sd-loading-dots {
			display: flex;
			gap: 6px;
			align-items: center;
			padding: 16px;
		}
		.sd-loading-dots.center { justify-content: center; }
		.sd-loading-dots span {
			width: 7px;
			height: 7px;
			border-radius: 50%;
			background: var(--text-muted);
			animation: sd-bounce 1.2s infinite;
		}
		.sd-loading-dots span:nth-child(2) { animation-delay: 0.2s; }
		.sd-loading-dots span:nth-child(3) { animation-delay: 0.4s; }
		@keyframes sd-bounce {
			0%, 80%, 100% { transform: scale(0.8); opacity: 0.4; }
			40%            { transform: scale(1.2); opacity: 1;   }
		}
		.sd-no-tech {
			font-size: 13px;
			color: var(--text-muted);
			padding: 16px;
		}

		</style>`).appendTo('head');
	}
}