// fleet/fleet/page/support_dashboard_chat/support_dashboard_chat.js
frappe.provide('fleet.support_dashboard_chat');

frappe.pages['support-dashboard-chat'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Support Dashboard',
		single_column: true,
	});
	$(wrapper).addClass('sd-support-dashboard-chat-page');
	fleet.support_dashboard_chat.remove_page_chrome(wrapper);
	fleet.support_dashboard_chat.init(wrapper);
};

frappe.pages['support-dashboard-chat'].on_page_show = function (wrapper) {
	fleet.support_dashboard_chat.remove_page_chrome(wrapper);
	if (!fleet.support_dashboard_chat.instance) return;
	const instance = fleet.support_dashboard_chat.instance;
	const opts = frappe.route_options || {};
	const preselect   = opts.technician  || null;
	const auto_unread = opts.auto_unread || false;
	instance._load_technicians_then(function () {
		if (preselect) {
			const tech = instance.technicians.find(t => t.name === preselect);
			if (tech) instance._select_technician(tech, auto_unread);
			frappe.route_options = {};
		}
	});
};

fleet.support_dashboard_chat.init = function (wrapper) {
	fleet.support_dashboard_chat.instance = new SupportDashboardChat(wrapper);
};

fleet.support_dashboard_chat.remove_page_chrome = function (wrapper) {
	$(wrapper).find('.page-head').remove();
	$('body > footer, .main-section > footer').remove();
};

const STATUS_COLORS = {
	'Pending':     '#e67e22',
	'In Progress': '#2566cd',
	'In Review':   '#00bcd4',
	'On Hold':     '#9b59b6',
	'Completed':   '#037a2f',
	'Cancelled':   '#e01f1f',
};

class SupportDashboardChat {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.$main = $(wrapper).find('.page-content');
		this.technicians    = [];
		this.selected_tech  = null;
		this.selected_job   = null;
		this.jobs           = [];
		this.show_completed_tasks = false;
		this.realtime_bound = false;
		this._inject_styles();
		this._render_shell();
		this._load_technicians_then();
		this._bind_realtime();
		this._bind_filters();
		this._bind_copy();
	}

	_render_shell() {
		this.$main.html(`
			<div class="sd-root">
				<div class="sd-topbar">
					<div class="sd-tech-list" id="sd-tech-list">
						<div class="sd-loading-dots"><span></span><span></span><span></span></div>
					</div>
				</div>
				<div class="sd-body">
					<div class="sd-jobs-panel" id="sd-jobs-panel">
							<div class="sd-jobs-header">
								<span id="sd-jobs-title">Select a technician</span>
								<label class="sd-completed-toggle">
									<input type="checkbox" id="sd-show-completed-tasks">
									<span>Completed</span>
								</label>
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
			const color    = COLORS[idx % COLORS.length];
			const initials = (tech.full_name || tech.name).split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
			const avatar   = tech.user_image
				? `<img src="${tech.user_image}" class="sd-tech-avatar-img" alt="${initials}">`
				: `<div class="sd-tech-avatar-initials" style="background:linear-gradient(135deg,${color}dd,${color}88)">${initials}</div>`;
			const unread    = parseInt(tech.total_unread || 0);
			const pending   = parseInt(tech.pending      || 0);
			const completed = parseInt(tech.completed    || 0);
			const badge     = `<span class="sd-tech-unread ${unread ? '' : 'sd-hidden'}" data-tech="${tech.name}">${unread}</span>`;
			const $card = $(`
				<div class="sd-tech-card" data-tech="${tech.name}">
					${badge}
					<div class="sd-tech-avatar">${avatar}</div>
					<div class="sd-tech-info">
						<div class="sd-tech-name">${frappe.utils.escape_html(tech.full_name || tech.name)}</div>
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
		if (this.selected_tech) {
			$(`.sd-tech-card[data-tech="${this.selected_tech.name}"]`).addClass('active');
		}
	}

	_select_technician(tech, auto_unread = false) {
		this.selected_tech = tech;
		this.selected_job  = null;
		$('.sd-tech-card').removeClass('active');
		$(`.sd-tech-card[data-tech="${tech.name}"]`).addClass('active');
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
		$('#sd-jobs-list').html(`<div class="sd-loading-dots center"><span></span><span></span><span></span></div>`);
		this._load_jobs(tech.name, auto_unread);
	}

	_load_jobs(technician, auto_unread = false) {
		frappe.call({
			method: 'fleet.api.dashboard_chat.get_technician_jobs',
			args: {
				technician,
				show_completed: this.show_completed_tasks ? 1 : 0,
			},
			callback: (r) => {
				const jobs = r.message || [];
				this.jobs = jobs.filter(job => {
					return this.show_completed_tasks
						? job.status === 'Completed'
						: job.status !== 'Completed';
				});
				$('#sd-jobs-count').text(`${this.jobs.length} job${this.jobs.length !== 1 ? 's' : ''}`);
				this._render_jobs();
				if (auto_unread) {
					const first_unread = this.jobs.find(j => parseInt(j.unread_count_support || 0) > 0);
					if (first_unread) this._select_job(first_unread);
				}
			},
		});
	}

	_bind_filters() {
		$(this.$main).on('change', '#sd-show-completed-tasks', (e) => {
			this.show_completed_tasks = $(e.currentTarget).is(':checked');
			this.selected_job = null;
			$('#sd-chat-panel').html(`
				<div class="sd-chat-empty">
					<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
						<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
					</svg>
					<h3>Select a job to start chatting</h3>
					<p>Messages will appear here</p>
				</div>
			`);
			if (!this.selected_tech) return;
			$('#sd-jobs-list').html(`<div class="sd-loading-dots center"><span></span><span></span><span></span></div>`);
			this._load_jobs(this.selected_tech.name);
		});
	}

	_render_jobs() {
		const $list = $('#sd-jobs-list');
		$list.empty();
		if (!this.jobs.length) {
			const empty_label = this.show_completed_tasks ? 'No completed jobs found' : 'No active jobs found';
			$list.html(`
				<div class="sd-empty-state">
					<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
						<circle cx="12" cy="12" r="10"/>
						<line x1="12" y1="8" x2="12" y2="12"/>
						<line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
					<p>${empty_label}</p>
				</div>
			`);
			return;
		}

		// Group jobs by task, preserving order
		const task_order = [];
		const task_groups = {};
		this.jobs.forEach(job => {
			const key = job.task || '__none__';
			if (!task_groups[key]) {
				task_order.push(key);
				task_groups[key] = { jobs: [], subject: job.task_subject || job.task || '', date: job.task_date || '' };
			}
			task_groups[key].jobs.push(job);
		});

		task_order.forEach((task_key, t_idx) => {
			const group    = task_groups[task_key];
			const job_count = group.jobs.length;
			const group_id  = `sd-task-group-${t_idx}`;

			// Format date
			const date_str = group.date
				? frappe.datetime.str_to_user(group.date)
				: '';

			// Task header row — click to collapse/expand
			const WS_COLORS = {
				'Open':           '#2490ef',
				'Working':        '#7b5ea7',
				'Pending Review': '#e67e22',
				'Overdue':        '#e01f1f',
				'Completed':      '#037a2f',
				'Cancelled':      '#94a3b8',
				'Template':       '#64748b',
			};
			const ws      = this._get_group_status(group.jobs);
			const ws_clr  = WS_COLORS[ws] || '#64748b';
			const ws_badge = ws
				? `<span class="sd-task-ws-badge" style="background:${ws_clr}22;color:${ws_clr}">${frappe.utils.escape_html(ws)}</span>`
				: '';

			const $header = $(`
				<div class="sd-task-header" data-group="${group_id}" data-task="${frappe.utils.escape_html(task_key)}">
					<div class="sd-task-header-left">
						<svg class="sd-task-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
						<span class="sd-task-subject">${frappe.utils.escape_html(group.subject)}</span>
					</div>
					<div class="sd-task-header-right">
						${ws_badge}
						${date_str ? `<span class="sd-task-date">${date_str}</span>` : ''}
						<span class="sd-task-count">${job_count} job${job_count !== 1 ? 's' : ''}</span>
					</div>
				</div>
			`);

			const $group_body = $(`<div class="sd-task-group-body" id="${group_id}"></div>`);

			$header.on('click', () => {
				const $body    = $(`#${group_id}`);
				const $chevron = $header.find('.sd-task-chevron');
				const is_open  = $body.is(':visible');
				$body.slideToggle(150);
				$chevron.css('transform', is_open ? 'rotate(-90deg)' : 'rotate(0deg)');
			});

			$list.append($header);
			$list.append($group_body);

			// Render jobs inside group
			group.jobs.forEach((job) => {
				const unread    = parseInt(job.unread_count_support || 0);
				const dot_color = STATUS_COLORS[job.status] || '#94a3b8';
				const pos_label = (job.task_job_count > 1)
					? `<span class="sd-job-pos">${job.job_position}/${job.task_job_count}</span>`
					: '';

				const $item = $(`
					<div class="sd-job-item" data-job="${job.name}">
						<div class="sd-job-status-dot" style="background:${dot_color}"></div>
						<div class="sd-job-content">
							<div class="sd-job-top">
								<span class="sd-job-title">${frappe.utils.escape_html(job.title || job.name)}</span>
								<span class="sd-job-time">${frappe.datetime.prettyDate(job.modified)}</span>
							</div>
							<div class="sd-job-footer">
								${pos_label}
								<span class="sd-job-status-tag" style="color:${dot_color}">${frappe.utils.escape_html(job.status)}</span>
								<span class="sd-vehicle-section">${job.vehicle_number ? `<span class="sd-job-action">${frappe.utils.escape_html(job.vehicle_number)}</span>` : ''}</span>
							</div>
						</div>
						<div class="sd-job-unread ${unread ? '' : 'sd-hidden'}" data-job-unread="${job.name}">${unread}</div>
					</div>
				`);
				$item.on('click', () => this._select_job(job));
				$group_body.append($item);
			});
		});
	}

	_get_group_status(jobs) {
		const statuses = [...new Set(jobs.map(job => job.status).filter(Boolean))];
		if (!statuses.length) return '';
		if (statuses.length === 1) return statuses[0];

		const priority = ['In Review', 'In Progress', 'On Hold', 'Pending', 'Completed', 'Cancelled'];
		return priority.find(status => statuses.includes(status)) || statuses[0];
	}

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
		if (this.selected_tech) this._refresh_tech_badge(this.selected_tech.name);
		this._render_chat_panel(job);
		this._load_messages(job.name);
	}

	_render_chat_panel(job) {
		const dot = STATUS_COLORS[job.status] || '#94a3b8';
		$('#sd-chat-panel').html(`
			<div class="sd-chat-wrapper">
				<div class="sd-chat-header">
					<div class="sd-chat-header-left">
						<div class="sd-chat-job-title">${frappe.utils.escape_html(job.title || job.name)}</div>
						<div class="sd-chat-job-meta">
							<span class="sd-chat-status-dot" style="background:${dot}"></span>
							<span class="sd-chat-status-text" style="color:${dot};font-weight:600">${frappe.utils.escape_html(job.status)}</span>
							<span class="sd-meta-sep">·</span>
							<span>${frappe.utils.escape_html(job.task_subject || job.task || '')}</span>
							<span class="sd-vehicle-section">${job.vehicle_number ? `<span class="sd-meta-sep">·</span><span class="sd-vehicle-tag">🚗 ${frappe.utils.escape_html(job.vehicle_number)}</span>` : ''}</span>
							${job.task_type && job.task_type !== 'None' ? `<span class="sd-meta-sep">·</span><span>${frappe.utils.escape_html(job.task_type)}</span>` : ''}
							${job.task_job_count > 1 ? `<span class="sd-meta-sep">·</span><span class="sd-chat-pos">${job.job_position}/${job.task_job_count}</span>` : ''}
						</div>
					</div>
					<div class="sd-chat-header-right">
						${job.task ? `<button class="sd-open-job-btn" onclick="frappe.set_route('Form','Task','${frappe.utils.escape_html(job.task)}')">Open Task ↗</button>` : ''}
						<button class="sd-open-job-btn" onclick="frappe.set_route('Form','Job','${frappe.utils.escape_html(job.name)}')">Open Job ↗</button>
					</div>
				</div>
				<div class="sd-messages-wrap" id="sd-messages-wrap">
					<div class="sd-messages-list" id="sd-messages-list">
						<div class="sd-msgs-loading">
							<div class="sd-loading-dots center"><span></span><span></span><span></span></div>
						</div>
					</div>
				</div>
				<div class="sd-chat-input-wrap">
					<textarea id="sd-chat-input" class="sd-chat-input" placeholder="Type a message..." rows="1"></textarea>
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
				if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._send_message(); }
			})
			.on('input', function () {
				this.style.height = '44px';
				this.style.height = Math.min(this.scrollHeight, 120) + 'px';
			});
		$('#sd-send-btn').on('click', () => this._send_message());
	}

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
				job:         job.name,
				message:     message,
				sender_name: frappe.session.user_fullname || frappe.session.user,
				role:        'Support',
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

	_append_bubble(msg) {
		const $list = $('#sd-messages-list');
		$list.find('.sd-msgs-empty, .sd-msgs-loading').remove();
		const role       = msg.sender_role || msg.role || 'Support';
		const is_support = role === 'Support';
		const name       = msg.sender_name || msg.sender || '?';
		const content    = msg.message    || msg.content || '';
		const time       = msg.creation ? frappe.datetime.str_to_user(msg.creation, true) : 'Just now';
		const _NO_COPY = new Set(['Make', 'Model', 'Color', 'Type']);
		const _COPY_ICON = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7.5 3H14.6C16.84 3 17.96 3 18.816 3.436C19.569 3.819 20.18 4.431 20.564 5.184C21 6.04 21 7.16 21 9.4V16.5M6.2 21H14.3C15.42 21 15.98 21 16.408 20.782C16.784 20.59 17.09 20.284 17.282 19.908C17.5 19.48 17.5 18.92 17.5 17.8V9.7C17.5 8.58 17.5 8.02 17.282 7.592C17.09 7.216 16.784 6.91 16.408 6.718C15.98 6.5 15.42 6.5 14.3 6.5H6.2C5.08 6.5 4.52 6.5 4.092 6.718C3.716 6.91 3.41 7.216 3.218 7.592C3 8.02 3 8.58 3 9.7V17.8C3 18.92 3 19.48 3.218 19.908C3.41 20.284 3.716 20.59 4.092 20.782C4.52 21 5.08 21 6.2 21Z"/></svg>`;
		const renderLine = (line) => {
			const escaped = frappe.utils.escape_html(line).replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
			const m = line.match(/^([^:]+): (.+)$/);
			if (m) {
				const rawKey  = m[1];
				const rawVal  = m[2];
				const safeKey = frappe.utils.escape_html(rawKey);
				const safeVal = frappe.utils.escape_html(rawVal);

				if (_NO_COPY.has(rawKey)) return `${safeKey}: ${safeVal}`;

				// Item lines are "CODE - BRAND" — copy only the code
				const dashIdx = rawVal.indexOf(' - ');
				const copyVal = dashIdx !== -1 ? rawVal.slice(0, dashIdx) : rawVal;

				return `${safeKey}: <span class="sd-copy-wrap">${safeVal}<button class="sd-copy-btn" data-copy="${frappe.utils.escape_html(copyVal)}" title="Copy">${_COPY_ICON}</button></span>`;
			}
			return escaped;
		};
		const rendered = this._render_update_message(content, renderLine);
		$list.append(`
			<div class="sd-bubble-row ${is_support ? 'mine' : 'theirs'}">
				<div class="sd-bubble-wrap">
					<div class="sd-bubble-name ${is_support ? 'sd-name-right' : ''}">${frappe.utils.escape_html(name)}</div>
					<div class="sd-bubble ${is_support ? 'sd-bubble-mine' : 'sd-bubble-theirs'}">
						${rendered}
					</div>
					<div class="sd-bubble-time ${is_support ? 'sd-time-right' : ''}">${time}</div>
				</div>
			</div>
		`);
	}

	_render_update_message(content, renderLine) {
		const parts = [];
		let activeSection = null;
		const flushSection = () => {
			if (!activeSection) return;
			const className = activeSection.type === 'installed' ? 'sd-update-installed' : 'sd-update-removed';
			parts.push(`<div class="sd-update-section ${className}">${activeSection.lines.join('')}</div>`);
			activeSection = null;
		};

		content.split('\n').forEach((line) => {
			if (!line.trim()) return;

			if (line === 'Installed:' || line === 'Removed:') {
				flushSection();
				activeSection = {
					type: line === 'Installed:' ? 'installed' : 'removed',
					lines: [`<div class="sd-update-section-title">${frappe.utils.escape_html(line)}</div>`],
				};
				return;
			}

			const renderedLine = renderLine(line);
			if (activeSection) {
				if (renderedLine.trim()) {
					activeSection.lines.push(`<div class="sd-update-line">${renderedLine}</div>`);
				}
			} else {
				parts.push(renderedLine);
			}
		});

		flushSection();
		return parts.join('');
	}

	_scroll_to_bottom() {
		const $wrap = $('#sd-messages-wrap');
		if ($wrap.length) $wrap.scrollTop($wrap[0].scrollHeight);
	}

	_bind_realtime() {
		if (this.realtime_bound) return;
		this.realtime_bound = true;
		frappe.realtime.on('support_dashboard_new_message', (data) => {
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
				if ((data.sender_role || data.role) === 'Technician') {
					// Update cached job unread count (persists across re-renders)
					const cachedJob = this.jobs.find(j => j.name === data.job);
					if (cachedJob) cachedJob.unread_count_support = (cachedJob.unread_count_support || 0) + 1;

					// Local +1 on job badge if element is currently in the DOM
					const $job_badge = $(`.sd-job-unread[data-job-unread="${data.job}"]`);
					if ($job_badge.length) {
						$job_badge.text((parseInt($job_badge.text()) || 0) + 1).removeClass('sd-hidden');
					}

					// Local +1 on tech card badge (data-tech = user email, same as tech_user)
					const tech_name = data.tech_user || data.sent_by || (this.selected_tech && this.selected_tech.name);
					if (tech_name) {
						const $tech_badge = $(`.sd-tech-unread[data-tech="${tech_name}"]`);
						$tech_badge.text((parseInt($tech_badge.text()) || 0) + 1).removeClass('sd-hidden');
					}
				}
				frappe.show_alert({
					message: `\u{1F4AC} ${data.sender_name || data.sent_by}: ${(data.content || data.message || '').slice(0, 60)}`,
					indicator: 'blue',
				}, 5);
			}
		});
		frappe.realtime.on('support_dashboard_read', (data) => {
			$(`.sd-job-unread[data-job-unread="${data.job}"]`).text('0').addClass('sd-hidden');
		});

		frappe.realtime.on('job_details_updated', (data) => {
			// Update the cached job object
			const job = this.jobs.find(j => j.name === data.job);
			if (!job) return;

			if (data.vehicle_number !== undefined) job.vehicle_number = data.vehicle_number;
			if (data.make  !== undefined) job.make  = data.make;
			if (data.model !== undefined) job.model = data.model;
			if (data.color !== undefined) job.color = data.color;
			if (data.type  !== undefined) job.type  = data.type;
			if (data.status !== undefined) job.status = data.status;

			const $item   = $(`.sd-job-item[data-job="${data.job}"]`);
			const $footer = $item.find('.sd-job-footer');

			// Update status dot + tag in job list
			if ($item.length && data.status !== undefined) {
				const dot_color = STATUS_COLORS[data.status] || '#94a3b8';
				$item.find('.sd-job-status-dot').css('background', dot_color);
				$item.find('.sd-job-status-tag').css('color', dot_color).text(data.status);
			}

			// Update vehicle number badge in the job list item
			if ($item.length) {
				$footer.find('.sd-vehicle-section').html(
					job.vehicle_number
						? `<span class="sd-job-action">${frappe.utils.escape_html(job.vehicle_number)}</span>`
						: ''
				);
			}

			// Update chat header if this job is currently open
			if (this.selected_job && this.selected_job.name === data.job) {
				Object.assign(this.selected_job, job);
				const $meta = $('#sd-chat-panel .sd-chat-job-meta');

				if (data.status !== undefined) {
					const dot_color = STATUS_COLORS[data.status] || '#94a3b8';
					$meta.find('.sd-chat-status-dot').css('background', dot_color);
					$meta.find('.sd-chat-status-text').css('color', dot_color).text(data.status);
				}

				$meta.find('.sd-vehicle-section').html(
					job.vehicle_number
						? `<span class="sd-meta-sep">·</span><span class="sd-vehicle-tag">🚗 ${frappe.utils.escape_html(job.vehicle_number)}</span>`
						: ''
				);
			}
		});
	}

	_refresh_tech_badge(tech_user) {
		frappe.call({
			method: 'fleet.api.dashboard_chat.get_tech_unread_total',
			args: { tech_user },
			callback: (r) => {
				const total  = parseInt(r.message) || 0;
				const $badge = $(`.sd-tech-unread[data-tech="${tech_user}"]`);
				$badge.text(total);
				total > 0 ? $badge.removeClass('sd-hidden') : $badge.addClass('sd-hidden');
			},
		});
	}

	_bind_copy() {
		$(this.$main).on('click', '.sd-copy-btn', function () {
			const $btn  = $(this);
			const val   = $btn.attr('data-copy');
			const orig  = $btn.html();
			navigator.clipboard.writeText(val).then(() => {
				$btn.html('<span style="font-size:11px;font-weight:600;color:#28a745">✓</span>');
				setTimeout(() => $btn.html(orig), 1200);
			});
		});
	}

	_inject_styles() {
		if ($('#sd-chat-styles').length) return;
		$(`<style id="sd-chat-styles">
		.sd-support-dashboard-chat-page .page-head {
			display: none !important;
		}
		.sd-support-dashboard-chat-page .page-content {
			padding-top: 0;
		}
		.sd-support-dashboard-chat-page .container,
		.sd-support-dashboard-chat-page .page-body,
		.sd-support-dashboard-chat-page .page-wrapper,
		.sd-support-dashboard-chat-page .page-content {
			display: flex;
			flex-direction: column;
			flex: 1 1 auto;
			min-height: 0;
		}

		.sd-root {
			display: flex; flex-direction: column;
			height: calc(100vh - 86px);
			min-height: 0;
			background: var(--bg-color);
			border-radius: 8px; overflow: hidden;
			border: 1px solid var(--border-color);
		}
		.sd-topbar {
			padding: 8px 10px 6px;
			background: var(--fg-color);
			border-bottom: 1px solid var(--border-color);
			flex-shrink: 0;
		}
		.sd-tech-list {
			display: flex; flex-wrap: wrap; gap: 6px;
			align-items: flex-start;
			justify-content: center;
		}
		.sd-tech-card {
			position: relative; display: flex; flex-direction: row;
			align-items: center; gap: 4px; padding: 8px 8px;
			background: var(--control-bg);
			border: 1.5px solid var(--border-color);
			border-radius: 8px; cursor: pointer;
			flex: 0 0 180px; width: 180px; box-sizing: border-box;
			transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
			overflow: hidden;
		}
		.sd-tech-card:hover { border-color: var(--primary); background: var(--blue-50, #eff6ff); }
		.sd-tech-card.active {
			border-color: var(--primary); background: var(--blue-50, #eff6ff);
			box-shadow: 0 0 0 2px var(--blue-100, #dbeafe);
		}
		.sd-tech-avatar { flex-shrink: 0; width: 34px; height: 34px; border-radius: 50%; overflow: hidden; }
		.sd-tech-avatar-img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
		.sd-tech-avatar-initials {
			width: 34px; height: 34px; border-radius: 50%;
			color: white; font-size: 12px; font-weight: 700;
			display: flex; align-items: center; justify-content: center;
		}
		.sd-tech-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; justify-content: center; }
		.sd-tech-name {
			font-size: 11.5px; font-weight: 600; color: var(--text-color);
			line-height: 1.25; word-break: break-word; white-space: normal;
			display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
		}
		.sd-tech-stats { display: flex; flex-wrap: wrap; gap: 2px; align-items: center; }
		.stat-pill {
			display: inline-flex; align-items: center;
			font-size: 9.5px; font-weight: 600; padding: 1px 5px;
			border-radius: 8px; white-space: nowrap; line-height: 1.4; flex-shrink: 0;
		}
		.stat-pill.pending  { background: #f1f5f9; color: #475569; }
		.stat-pill.done     { background: #dcfce7; color: #15803d; }
		.sd-tech-unread {
			position: absolute; bottom: 2px; right: 2px;
			background: #ef4444; color: white;
			font-size: 13px; font-weight: 700;
			min-width: 24px; height: 24px; border-radius: 12px;
			display: flex; align-items: center; justify-content: center;
			padding: 0 6px; box-shadow: 0 0 0 2px var(--fg-color); z-index: 1;
		}
		.sd-hidden { display: none !important; }

		.sd-body { display: flex; flex: 1; overflow: hidden; }

		.sd-jobs-panel {
			width: 400px; flex-shrink: 0; display: flex; flex-direction: column;
			border-right: 1px solid var(--border-color); background: var(--fg-color);
		}
		.sd-jobs-header {
			min-height: 36px;
			padding: 8px 14px; border-bottom: 1px solid var(--border-color);
			display: grid;
			grid-template-columns: minmax(0, 1fr) max-content max-content;
			align-items: center;
			column-gap: 12px;
			font-weight: 600; font-size: 13px; color: var(--text-color); flex-shrink: 0;
		}
		#sd-jobs-title {
			display: block;
			line-height: 18px;
			min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
		}
		.sd-completed-toggle {
			display: grid;
			grid-template-columns: 14px max-content;
			align-items: center;
			column-gap: 6px;
			height: 8px;
			line-height: 18px;
			font-size: 11px; font-weight: 600; color: var(--text-muted);
			white-space: nowrap; cursor: pointer;
		}
		.sd-completed-toggle input {
			display: block;
			width: 14px; height: 14px;
			margin: 0;
			accent-color: var(--primary);
			cursor: pointer;
		}
		.sd-jobs-count {
			display: block;
			font-size: 11px; line-height: 18px;
			color: var(--text-muted); font-weight: 400; flex-shrink: 0;
		}
		.sd-jobs-list { flex: 1; overflow-y: auto; }
		.sd-jobs-list::-webkit-scrollbar { width: 3px; }
		.sd-jobs-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 2px; }

		/* ── TASK GROUP HEADER ── */
		.sd-task-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 7px 14px 6px;
			background: #1e293b;
			border-bottom: 1px solid #334155;
			cursor: pointer;
			user-select: none;
			position: sticky;
			top: 0;
			z-index: 2;
		}
		.sd-task-header:hover { background: #273548; }
		.sd-task-header-left {
			display: flex; align-items: center; gap: 5px;
			min-width: 0;
		}
		.sd-task-chevron {
			flex-shrink: 0; color: #94a3b8;
			transition: transform 0.15s;
		}
		.sd-task-subject {
			font-size: 11px; font-weight: 700;
			color: #cbd5e1;
			text-transform: uppercase;
			letter-spacing: 0.05em;
			white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
		}
		.sd-task-header-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
		.sd-task-date {
			font-size: 10px; color: #94a3b8;
			white-space: nowrap;
		}
		.sd-task-count {
			font-size: 10px; font-weight: 600;
			padding: 1px 6px; border-radius: 8px;
			background: #334155;
			color: #94a3b8;
			white-space: nowrap;
		}
		.sd-task-ws-badge {
			font-size: 9.5px; font-weight: 700;
			padding: 1px 7px; border-radius: 8px;
			white-space: nowrap; letter-spacing: 0.02em;
		}
		.sd-task-group-body { }

		/* ── JOB ITEM ── */
		.sd-job-item {
			display: flex; align-items: flex-start; gap: 10px;
			padding: 10px 14px; cursor: pointer;
			border-bottom: 1px solid var(--border-color);
			transition: background 0.1s; position: relative;
		}
		.sd-job-item:hover  { background: var(--blue-50, #eff6ff); }
		.sd-job-item.active { background: var(--blue-50, #eff6ff); border-left: 3px solid var(--primary); }
		.sd-job-status-dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
		.sd-job-content { flex: 1; min-width: 0; padding-right: 30px; }
		.sd-job-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }
		.sd-job-title { font-size: 12px; font-weight: 600; color: var(--text-color); white-space: nowrap; overflow: hidden; max-width: 200px; }
		.sd-job-time  { font-size: 10px; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }
		.sd-job-bottom { display: flex; gap: 5px; align-items: center; margin-top: 3px; flex-wrap: wrap; }

		/* Position badge — e.g. "2/4" */
		.sd-job-pos {
			display: inline-flex; align-items: center;
			font-size: 9.5px; font-weight: 700;
			padding: 1px 6px; border-radius: 5px;
			background: var(--blue-100, #dbeafe);
			color: var(--blue-600, #2563eb);
			white-space: nowrap; flex-shrink: 0; letter-spacing: 0.02em;
		}
		.sd-job-meta    { font-size: 11px; color: var(--text-muted); }
		.sd-job-vehicle { font-size: 11px; color: var(--text-muted); }
		.sd-job-footer  { display: flex; gap: 6px; margin-top: 4px; align-items: center; }
		.sd-job-status-tag { font-size: 10px; font-weight: 600; }
		.sd-job-action {
			font-size: 10px; background: var(--blue-100, #dbeafe);
			color: var(--blue-600, #2563eb); padding: 1px 6px; border-radius: 4px;
		}
		.sd-job-unread {
			position: absolute; right: 14px; bottom: 18px;
			background: #ef4444; color: white; font-size: 12px; font-weight: 700;
			min-width: 22px; height: 22px; border-radius: 11px;
			display: flex; align-items: center; justify-content: center;
			padding: 0 6px; flex-shrink: 0;
		}

		.sd-chat-panel { flex: 1; display: flex; flex-direction: column; background: var(--bg-color); overflow: hidden; }
		.sd-chat-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 12px; color: var(--text-muted); }
		.sd-chat-empty h3 { font-size: 16px; font-weight: 600; color: var(--text-color); margin: 0; }
		.sd-chat-empty p  { font-size: 13px; margin: 0; }
		.sd-chat-wrapper  { display: flex; flex-direction: column; height: 100%; }
		.sd-chat-header {
			padding: 10px 18px; background: var(--fg-color);
			border-bottom: 1px solid var(--border-color);
			display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
		}
		.sd-chat-job-title { font-size: 14px; font-weight: 700; color: var(--text-color); }
		.sd-chat-job-meta  { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-muted); margin-top: 3px; flex-wrap: wrap; }
		.sd-chat-status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
		.sd-chat-pos { font-size: 10px; font-weight: 700; color: var(--blue-600, #2563eb); }
		.sd-meta-sep { color: var(--border-color); }
		.sd-open-job-btn {
			font-size: 11px; font-weight: 600; padding: 5px 12px; border-radius: 6px;
			border: 1px solid var(--border-color); background: var(--control-bg);
			color: var(--text-color); cursor: pointer; transition: all 0.15s; white-space: nowrap;
		}
		.sd-open-job-btn:hover { border-color: var(--primary); color: var(--primary); }

		.sd-messages-wrap { flex: 1; overflow-y: auto; padding: 16px 18px; }
		.sd-messages-wrap::-webkit-scrollbar { width: 4px; }
		.sd-messages-wrap::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 2px; }
		.sd-messages-list { display: flex; flex-direction: column; gap: 12px; }
		.sd-msgs-empty, .sd-msgs-loading { text-align: center; color: var(--text-muted); font-size: 13px; padding: 40px 0; }

		.sd-bubble-row { display: flex; align-items: flex-end; }
		.sd-bubble-row.mine   { flex-direction: row-reverse; }
		.sd-bubble-row.theirs { flex-direction: row; }
		.sd-bubble-wrap { display: flex; flex-direction: column; max-width: 65%; }
		.sd-bubble-name { font-size: 11px; color: var(--text-muted); margin-bottom: 3px; font-weight: 600; }
		.sd-name-right  { text-align: right; }
		.sd-bubble { padding: 9px 13px; font-size: 13px; line-height: 1.5; word-break: break-word; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
		.sd-bubble-mine   { background: var(--primary); color: white; border-radius: 14px 14px 2px 14px; }
		.sd-bubble-theirs { background: var(--fg-color); color: var(--text-color); border: 1px solid var(--border-color); border-radius: 14px 14px 14px 2px; }
		.sd-update-section {
			margin: 3px 0;
			padding: 7px 10px;
			border-radius: 8px;
			border: 1px solid transparent;
		}
		.sd-update-section-title {
			font-weight: 700;
			margin-bottom: 4px;
			line-height: 1.25;
		}
		.sd-update-line {
			line-height: 1.35;
			margin: 1px 0;
		}
		.sd-update-installed {
			background: #dcfce7;
			border-color: #86efac;
			color: #14532d;
		}
		.sd-update-removed {
			background: #fee2e2;
			border-color: #fca5a5;
			color: #7f1d1d;
		}
		.sd-bubble-time { font-size: 10px; color: var(--text-muted); margin-top: 3px; }
		.sd-time-right  { text-align: right; }

		.sd-chat-input-wrap {
			padding: 10px 14px; background: var(--fg-color);
			border-top: 1px solid var(--border-color);
			display: flex; gap: 10px; align-items: flex-end; flex-shrink: 0;
		}
		.sd-chat-input {
			flex: 1; resize: none; min-height: 44px; max-height: 120px;
			border: 1px solid var(--border-color); border-radius: 22px;
			padding: 10px 16px; font-size: 13px; font-family: var(--font-stack);
			background: var(--control-bg); color: var(--text-color);
			outline: none; transition: border-color 0.15s; line-height: 1.4;
		}
		.sd-chat-input:focus { border-color: var(--primary); }
		.sd-send-btn {
			width: 44px; height: 44px; border-radius: 50%; background: var(--primary);
			color: white; border: none; cursor: pointer;
			display: flex; align-items: center; justify-content: center;
			flex-shrink: 0; transition: all 0.15s;
		}
		.sd-send-btn:hover    { filter: brightness(1.1); transform: scale(1.05); }
		.sd-send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

		.sd-empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; gap: 12px; color: var(--text-muted); text-align: center; }
		.sd-empty-state p { font-size: 13px; margin: 0; }
		.sd-loading-dots { display: flex; gap: 6px; align-items: center; padding: 16px; }
		.sd-loading-dots.center { justify-content: center; }
		.sd-loading-dots span { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); animation: sd-bounce 1.2s infinite; }
		.sd-loading-dots span:nth-child(2) { animation-delay: 0.2s; }
		.sd-loading-dots span:nth-child(3) { animation-delay: 0.4s; }
		@keyframes sd-bounce { 0%,80%,100% { transform:scale(0.8); opacity:0.4; } 40% { transform:scale(1.2); opacity:1; } }
		.sd-no-tech { font-size: 13px; color: var(--text-muted); padding: 12px; }

		@media (max-width: 900px) {
			.sd-root { height: auto; min-height: calc(100vh - 86px); }
			.sd-body { flex-direction: column; }
			.sd-jobs-panel { width: 100%; max-height: 260px; border-right: none; border-bottom: 1px solid var(--border-color); }
			.sd-tech-card { flex: 0 0 160px; width: 160px; }
		}
		@media (max-width: 600px) {
			.sd-tech-card { flex: 0 0 140px; width: 140px; padding: 6px 8px; gap: 6px; }
			.sd-tech-avatar, .sd-tech-avatar-initials { width: 28px; height: 28px; font-size: 10px; }
			.sd-tech-name { font-size: 10.5px; }
			.stat-pill { font-size: 9px; padding: 1px 4px; }
			.sd-jobs-panel { max-height: 200px; }
			.sd-messages-wrap { padding: 10px 12px; }
			.sd-bubble { font-size: 12px; padding: 7px 11px; }
		}

		.sd-copy-wrap {
			display: inline-flex; align-items: center; gap: 4px;
		}
		.sd-copy-btn {
			background: none; border: none; cursor: pointer;
			padding: 0 2px; line-height: 1;
			color: #94a3b8; opacity: 0.6;
			transition: opacity 0.15s, color 0.15s;
			vertical-align: middle;
		}
		.sd-copy-btn:hover { opacity: 1; color: #2566cd; }
		.sd-copy-btn svg { display: inline-block; vertical-align: middle; }

		</style>`).appendTo('head');
	}
}
