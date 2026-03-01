// fleet/fleet/page/support_dashboard/support_dashboard.js
// Grid dashboard — clicking a card routes to support-dashboard-ch with that technician pre-selected

frappe.pages['support-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		title: 'Support Dashboard',
		parent: wrapper,
		single_column: true,
	});

	wrapper.page_obj = page;

	page.set_primary_action('Refresh', () => dashboard.load());
	page.add_menu_item('New Task', () => frappe.new_doc('Task'));
	page.add_menu_item('Material Transfer', () => frappe.new_doc('Material Request'));

	let search_field = page.add_field({
		label: 'Search Technician',
		fieldtype: 'Data',
		fieldname: 'search',
		change() {
			dashboard.filter(search_field.get_value());
		}
	});

	$('<style id="sd-styles">' + SD_CSS + '</style>').appendTo('head');

	let $body = $(wrapper).find('.page-content');
	$body.css({ padding: '16px 20px', minHeight: '100vh' });
	$body.html(`
		<div id="sd-root">
			<div id="sd-header">
				<span class="sd-heading-label">All Technicians</span>
				<span id="sd-total-badge">0</span>
			</div>
			<div id="sd-grid"></div>
		</div>
	`);

	var dashboard = {
		all_techs: [],

		load: function () {
			$('#sd-grid').html(SD_LOADING);
			frappe.call({
				method: 'fleet.api.dashboard.get_dashboard_data',
				callback: function (r) {
					if (!r.message || !r.message.length) {
						$('#sd-grid').html('<div class="sd-empty">No technicians found.</div>');
						return;
					}
					dashboard.all_techs = r.message;
					dashboard.render(r.message);
				},
				error: function () {
					$('#sd-grid').html('<div class="sd-empty">Error loading dashboard.</div>');
				}
			});
		},

		render: function (techs) {
			let $grid = $('#sd-grid');
			$grid.empty();
			$('#sd-total-badge').text(techs.length);
			techs.forEach(function (tech, i) {
				$grid.append(SD_card(tech, i));
			});
			dashboard.bind_events();
		},

		filter: function (query) {
			if (!dashboard.all_techs.length) return;
			let q = (query || '').toLowerCase().trim();
			let filtered = q
				? dashboard.all_techs.filter(t =>
					(t.employee_name || '').toLowerCase().includes(q) ||
					(t.department    || '').toLowerCase().includes(q) ||
					(t.cell_number   || '').toLowerCase().includes(q)
				)
				: dashboard.all_techs;
			dashboard.render(filtered);
		},

		bind_events: function () {

			// open chat dashboard for this technician
			$('.sd-card').on('click', function () {
				const uid = $(this).data('uid');
				if (!uid) return;
				frappe.route_options = { technician: uid };
				frappe.set_route('support-dashboard-chat');
			});

			// Task list button
			$('.sd-task-btn').on('click', function (e) {
				e.stopPropagation();
				let uid    = $(this).data('uid');
				let filter = JSON.stringify(["like", "%" + uid + "%"]);
				frappe.set_route('List', 'Task', { _assign: filter });
			});

			// Profile button
			$('.sd-profile-btn').on('click', function (e) {
				e.stopPropagation();
				frappe.set_route('Form', 'Employee', $(this).data('emp'));
			});

			// Message button → open chat for this tech
			$('.sd-msg-btn').on('click', function (e) {
				e.stopPropagation();
				const uid = $(this).data('uid');
				if (!uid) return;
				frappe.route_options = { technician: uid };
				frappe.set_route('support-dashboard-chat');
			});
		}
	};

	// Realtime: legacy task chat
	frappe.realtime.on('task_unread_chat', function (data) {
		if (data.sent_by === frappe.session.user) return;
		let $card  = $(`.sd-card[data-uid="${data.sent_by}"]`);
		if (!$card.length) return;
		let $badge = $card.find('.sd-card-badge');
		$badge.text(parseInt($badge.text() || '0') + 1).show();
		$card.find('.sd-msg-btn').addClass('sd-msg-unread');
		$card.addClass('sd-card-flash');
		setTimeout(() => $card.removeClass('sd-card-flash'), 2000);
	});

	// Realtime: Job Message unread badge on grid card
	frappe.realtime.on('support_dashboard_new_message', function (data) {
		if (data.sent_by === frappe.session.user) return;
		const uid  = data.sent_by;
		let $card  = $(`.sd-card[data-uid="${uid}"]`);
		if (!$card.length) return;
		let $badge = $card.find('.sd-card-badge');
		$badge.text((parseInt($badge.text() || '0')) + 1).show();
		$card.find('.sd-msg-btn').addClass('sd-msg-unread');
		$card.addClass('sd-card-flash');
		setTimeout(() => $card.removeClass('sd-card-flash'), 2000);
	});

	dashboard.load();
	setInterval(() => dashboard.load(), 60000);
};


//  ITEM TYPE ICON
function SD_item_icon(icon_name, item_type) {
	if (icon_name) {
		return frappe.utils.icon(icon_name, 'md');
	}
	var letters = (item_type || '?').trim().split(/\s+/).map(function (w) { return w[0]; }).join('').slice(0, 2).toUpperCase();
	return '<span class="sd-inv-letters">' + letters + '</span>';
}

//  CARD BUILDER
function SD_card(tech, idx) {
	var COLORS = [
		'#2490ef', '#7b5ea7', '#e67e22', '#27ae60', '#e74c3c', '#16a085',
		'#d35400', '#2980b9', '#8e44ad', '#c0392b', '#1abc9c', '#f39c12',
		'#2ecc71', '#3498db', '#9b59b6', '#e91e63'
	];

	var color  = COLORS[idx % COLORS.length];
	var name   = tech.employee_name || tech.name    || 'Unknown';
	var mobile = tech.cell_number   || tech.mobile_no || '\u2014';
	var tasks  = tech.task_count    || 0;
	var unread = tech.unread_count  || 0;
	var uid    = tech.user_id       || '';
	var emp    = tech.name          || '';

	var uinfo       = (frappe.user_info && uid) ? frappe.user_info(uid) : null;
	var imgSrc      = tech.image || (uinfo && uinfo.image) || '';
	var ini         = SD_initials(name);

	var avatarInner = imgSrc
		? '<img src="' + imgSrc + '" alt="' + ini + '" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;" onerror="this.style.display=\'none\';this.parentNode.innerText=\'' + ini + '\'">'
		: ini;
	var avatarStyle = imgSrc ? '' : 'background:linear-gradient(135deg,' + color + 'dd,' + color + '88);';

	var inventory = tech.inventory || [];
	var invInner;
	if (inventory.length) {
		var chips = inventory.map(function (inv) {
			var icon = SD_item_icon(inv.icon || '', inv.item_type);
			return '<span class="sd-inv-chip" title="' + inv.item_type + ': ' + inv.qty + '">'
				+ '<span class="sd-inv-icon">' + icon + '</span>'
				+ '<span class="sd-inv-qty">' + inv.qty + '</span>'
				+ '</span>';
		});
		invInner = chips.join('<span class="sd-inv-sep"></span>');
	} else {
		invInner = '<span class="sd-inv-empty">\u2014</span>';
	}

	var badgeStyle = unread > 0 ? '' : 'display:none';
	var badgeText  = unread > 99 ? '99+' : unread;
	var msgClass   = 'sd-stat-btn sd-msg-btn' + (unread > 0 ? ' sd-msg-unread' : '');

	return (
		'<div class="sd-card" data-uid="' + uid + '" data-emp="' + emp + '" style="--sd-color:' + color + ';cursor:pointer;" title="Click to open chat">'

		+ '<div class="sd-card-badge" style="' + badgeStyle + '">' + badgeText + '</div>'

		+ '<div class="sd-avatar" style="' + avatarStyle + '">' + avatarInner + '</div>'

		+ '<div class="sd-name">' + frappe.utils.escape_html(name) + '</div>'

		+ '<div class="sd-mobile">'
		+ '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="sd-mobile-icon">'
		+ '<rect x="5" y="2" width="14" height="20" rx="2"/>'
		+ '<line x1="12" y1="18" x2="12.01" y2="18"/>'
		+ '</svg>'
		+ frappe.utils.escape_html(mobile)
		+ '</div>'

		+ '<div class="sd-inv-row">' + invInner + '</div>'

		+ '<div class="sd-divider"></div>'

		+ '<div class="sd-foot">'

		+ '<button class="sd-stat-btn sd-task-btn" data-uid="' + uid + '" title="' + tasks + ' open task' + (tasks !== 1 ? 's' : '') + '">'
		+ '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>'
		+ '<span>' + tasks + '</span>'
		+ '</button>'

		+ '<span class="sd-sep"></span>'

		+ '<button class="' + msgClass + '" data-uid="' + uid + '" title="Open chat">'
		+ '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
		+ '<span>' + unread + '</span>'
		+ '</button>'

		+ '<span class="sd-sep"></span>'

		+ '<button class="sd-stat-btn sd-profile-btn" data-emp="' + emp + '" title="Open Employee">'
		+ '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
		+ '</button>'

		+ '</div>'
		+ '</div>'
	);
}


//  HELPERS
function SD_initials(name) {
	var p = (name || '').trim().split(' ').filter(Boolean);
	if (!p.length) return '?';
	if (p.length === 1) return p[0][0].toUpperCase();
	return (p[0][0] + p[p.length - 1][0]).toUpperCase();
}

var SD_LOADING = '<div class="sd-loading"><div class="sd-spinner"></div><span>Loading\u2026</span></div>';


//  CSS
var SD_CSS = [

'#sd-root { font-family:var(--font-stack,"Inter",sans-serif); }',

'#sd-header { display:flex; align-items:center; gap:8px; margin-bottom:14px; }',
'.sd-heading-label { font-size:13px; font-weight:700; color:#1c1c1c; }',
'#sd-total-badge { background:#e8f3fd; color:#2490ef; font-size:11px; font-weight:700; border-radius:100px; padding:2px 9px; border:1px solid #c5d5f8; }',

'#sd-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; align-items:stretch; }',
'@media (max-width:1400px) { #sd-grid { grid-template-columns:repeat(4,1fr); } }',
'@media (max-width:1050px) { #sd-grid { grid-template-columns:repeat(3,1fr); } }',
'@media (max-width:700px)  { #sd-grid { grid-template-columns:repeat(2,1fr); } }',
'@media (max-width:420px)  { #sd-grid { grid-template-columns:1fr; } }',

'.sd-loading { grid-column:1/-1; display:flex; flex-direction:column; align-items:center; gap:12px; padding:60px 0; color:#8d99a6; font-size:12px; }',
'.sd-spinner { width:22px; height:22px; border:2px solid #e2e6ea; border-top-color:#2490ef; border-radius:50%; animation:sd-spin 0.7s linear infinite; }',
'@keyframes sd-spin { to { transform:rotate(360deg); } }',
'.sd-empty { grid-column:1/-1; text-align:center; padding:60px 0; color:#8d99a6; font-size:12px; }',

'.sd-card { background:#fff; border:1px solid #e2e6ea; border-radius:8px; padding:12px 10px 8px; display:flex; flex-direction:column; align-items:center; gap:4px; position:relative; overflow:visible; transition:transform 0.18s,box-shadow 0.18s,border-color 0.18s; animation:sd-up 0.3s ease both; min-height:0; }',
'.sd-card:hover { transform:translateY(-2px); box-shadow:0 5px 18px rgba(0,0,0,0.09); border-color:var(--sd-color,#2490ef); }',
'@keyframes sd-up { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }',
'.sd-card-flash { animation:sd-flash 0.4s ease 3; }',
'@keyframes sd-flash { 0%,100%{border-color:#e2e6ea} 50%{border-color:#e74c3c;box-shadow:0 0 0 3px rgba(231,76,60,.15)} }',

'.sd-card-badge { position:absolute; top:-6px; right:-6px; background:#e74c3c; color:#fff; font-size:9px; font-weight:700; min-width:16px; height:16px; border-radius:100px; display:flex; align-items:center; justify-content:center; padding:0 3px; border:2px solid #eef0f3; z-index:10; animation:sd-bounce 0.35s ease; }',
'@keyframes sd-bounce { 0%{transform:scale(0)} 70%{transform:scale(1.2)} 100%{transform:scale(1)} }',

'.sd-avatar { width:48px; height:48px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:17px; font-weight:700; color:#fff; overflow:hidden; border:2px solid #e2e6ea; flex-shrink:0; letter-spacing:0.5px; }',

'.sd-name { font-size:12px; font-weight:600; text-align:center; width:100%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#1c1c1c; margin-top:1px; }',
'.sd-mobile { font-size:10.5px; color:#525f7f; font-weight:500; text-align:center; width:100%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:flex; align-items:center; justify-content:center; gap:2px; }',
'.sd-mobile-icon { width:10px; height:10px; flex-shrink:0; }',

'.sd-inv-row { display:flex; align-items:center; justify-content:center; width:100%; min-height:26px; margin-top:1px; flex-wrap:nowrap; }',
'.sd-inv-empty { font-size:11px; color:#d0d5dd; line-height:26px; }',
'.sd-inv-chip { display:inline-flex; align-items:center; gap:3px; padding:3px 7px; border-radius:20px; background:#fff; cursor:default; }',
'.sd-inv-chip:not(:first-child) { margin-left:4px; }',
'.sd-inv-icon { display:flex; align-items:center; justify-content:center; width:16px; height:16px; color:#525f7f; }',
'.sd-inv-icon svg { width:16px; height:16px; }',
'.sd-inv-icon .icon { width:16px; height:16px; }',
'.sd-inv-qty { font-size:11px; font-weight:700; color:#1c1c1c; line-height:1; }',
'.sd-inv-letters { font-size:9px; font-weight:800; color:#525f7f; line-height:1; }',
'.sd-inv-sep { display:none; }',

'.sd-divider { width:100%; height:1px; background:#f0f1f3; margin-top:auto; margin-bottom:1px; }',

'.sd-foot { width:100%; display:flex; align-items:center; justify-content:center; gap:0; }',
'.sd-stat-btn { flex:1; height:24px; background:none; border:none; outline:none; display:flex; align-items:center; justify-content:center; gap:3px; font-size:10.5px; font-weight:600; color:#8d99a6; cursor:pointer; transition:color 0.15s; padding:0; font-family:inherit; }',
'.sd-stat-btn svg { width:12px; height:12px; flex-shrink:0; }',
'.sd-stat-btn:hover { color:#2490ef; }',
'.sd-sep { width:1px; height:12px; background:#dde1e7; flex-shrink:0; }',
'.sd-msg-unread { color:#e74c3c !important; }',
'.sd-msg-unread:hover { color:#c0392b !important; }',

].join('\n');