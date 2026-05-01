

frappe.listview_settings["Task"] = {
    onload(listview) {
        frappe.after_ajax(function () {
            const $sidebar = listview.page.wrapper.find(".layout-side-section");
            if ($sidebar.length && $sidebar.is(":visible")) {
                $(".page-head").find(".sidebar-toggle-btn").trigger("click");
            }
        });
        init_task_chat_list(listview);
    }
};

// init

function init_task_chat_list(listview) {

    if (listview.__task_chat_init) return;
    listview.__task_chat_init = true;

    add_chat_styles();
    bind_realtime_listener();

    sync_visible_rows(listview);

    listview.page.wrapper.on("list-refresh", () => {
        sync_visible_rows(listview);
    });
}

// realtime event

function bind_realtime_listener() {

    if (window.__task_chat_socket_bound) return;
    window.__task_chat_socket_bound = true;

    frappe.realtime.on("task_job_chat_list_update", data => {

        if (!data || data.sent_by === frappe.session.user) return;

        const task_name = data.task_name;
        const job_name  = data.job;

        const $row = get_row(task_name);
        if (!$row.length) return;

        increment_unread_count(task_name, job_name);

        const total = get_unread_count(task_name);

        show_indicator_on_row($row, total);

        show_browser_notification(task_name);

        frappe.show_alert({
            message: `New message in Task: ${task_name}`,
            indicator: "blue"
        }, 5);
    });
}

// find row

function get_row(task_name) {
    return $(`.list-row-checkbox[data-name="${task_name}"]`)
        .closest(".list-row-container");
}

// initia sync

function sync_visible_rows(listview) {

    const visible_tasks = listview.data.map(d => d.name);

    visible_tasks.forEach(task_name => {

        const local = get_unread_count(task_name);

        if (local > 0) {
            const $row = get_row(task_name);
            if ($row.length) show_indicator_on_row($row, local);
        }

        frappe.call({
            method: "fleet.api.chat.get_unread_count",
            args: { task_name },
            callback(r) {

                if (!r.message) return;

                const jobs = Object.keys(r.message);

                if (!jobs.length) return;

                jobs.forEach(job => {
                    increment_unread_count(task_name, job);
                });

                const total = get_unread_count(task_name);

                const $row = get_row(task_name);
                if ($row.length) show_indicator_on_row($row, total);
            }
        });
    });
}

// indicator ui

function show_indicator_on_row($row, count) {

    if (!$row.find(".task-chat-indicator").length) {
        $row.css("position", "relative");
        $row.append(`<div class="task-chat-indicator"></div>`);
    }

    update_badge($row, count);
}

function update_badge($row, count) {

    const $subject = $row.find(".level-item.ellipsis").first();

    $subject.find(".task-chat-badge").remove();

    if (count > 0) {
        $subject.append(`<span class="task-chat-badge">${count}</span>`);
    }
}

// local storage

function get_unread_count(task) {
    const data = JSON.parse(localStorage.getItem("task_chat_unread") || "{}");
    return Object.keys(data[task] || {}).length;
}

function increment_unread_count(task, job) {

    const data = JSON.parse(localStorage.getItem("task_chat_unread") || "{}");

    if (!data[task]) data[task] = {};

    data[task][job] = true;

    localStorage.setItem("task_chat_unread", JSON.stringify(data));
}

function clear_unread_count(task, job) {

    const data = JSON.parse(localStorage.getItem("task_chat_unread") || "{}");

    if (data[task]?.[job]) {
        delete data[task][job];

        if (!Object.keys(data[task]).length) delete data[task];

        localStorage.setItem("task_chat_unread", JSON.stringify(data));
    }
}

// called from task.js when chat opened
window.clear_task_chat_notification = function(task, job) {

    clear_unread_count(task, job);

    const $row = get_row(task);

    const remaining = get_unread_count(task);

    update_badge($row, remaining);
};

// notification

function show_browser_notification(task_name) {

    if (!("Notification" in window)) return;

    if (Notification.permission === "granted") {

        new Notification("Fleet Track - New Message", {
            body: `New chat message in Task: ${task_name}`,
            icon: "/assets/fleet/images/notification-icon.png",
            tag: task_name
        });

    } else if (Notification.permission !== "denied") {

        Notification.requestPermission().then(p => {
            if (p === "granted") show_browser_notification(task_name);
        });
    }
}

// style

function add_chat_styles() {

    if ($("#task-chat-style").length) return;

    $(`<style id="task-chat-style">

        .task-chat-indicator{
            position:absolute;
            top:8px;
            right:8px;
            width:10px;
            height:10px;
            background:var(--red-500);
            border-radius:50%;
            border:2px solid white;
            animation:pulse 1.5s infinite;
            z-index:5;
        }

        .task-chat-badge{
            background:var(--red-500);
            color:white;
            border-radius:10px;
            padding:2px 6px;
            font-size:10px;
            margin-left:6px;
        }

        @keyframes pulse{
            0%{transform:scale(1);opacity:1}
            50%{transform:scale(1.2);opacity:.7}
            100%{transform:scale(1);opacity:1}
        }

    </style>`).appendTo("head");
}