frappe.ui.form.on('Task', {
    // custom_assign_to(frm) {
    //     if (!frm.is_dirty()) return;
    //     frm.save();
    // },
    setup: function (frm) {
        frm.set_query("custom_address", function (doc) {
            return {
                filters: {
                    link_doctype: "Customer",
                    link_name: doc.custom_customer,
                },
            };
        });
    },
	custom_address: function (frm) {
		if (frm.doc.custom_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {
					address_dict: frm.doc.custom_address,
				},
				callback: function (r) {
					frm.set_value("custom_complete_address", r.message);
				},
			});
		}
		if (!frm.doc.address) {                             
			frm.set_value("custom_complete_address", "");
		}
	},
    refresh: function(frm) {
        // Render chat for each job row on form load
        frm.doc.custom_task_jobs?.forEach(row => {
            render_job_chat(frm, row.name);
        });
    }
});

frappe.ui.form.on('Task Job', {
    // Trigger chat render whenever a row is added/modified
    form_render: function(frm, cdt, cdn) {
        setTimeout(() => render_job_chat(frm, cdn), 100);
    }
});

// ══════════════════════════════════════════════════════════
//  MAIN: Render chat panel for each job row
// ══════════════════════════════════════════════════════════
function render_job_chat(frm, cdn) {
    // Find the grid row wrapper
    let grid_row = frm.fields_dict['custom_task_jobs']?.grid?.grid_rows_by_docname?.[cdn];
    if (!grid_row || !grid_row.wrapper) return;

    let $row_wrapper = $(grid_row.wrapper);
    
    // Avoid duplicate rendering
    if ($row_wrapper.find('.job-chat-section').length > 0) return;

    let row = frappe.get_doc('Task Job', cdn);
    
    // Build the chat section HTML (matches your screenshot styling)
    let $chat_section = $(`
        <div class="job-chat-section" data-cdn="${cdn}" style="
            border-top: 1px solid #e8ecef;
            background: var(--gray-50);
            margin: 0 -15px;
            padding: 0;
            font-family: var(--font-stack);
        ">
            <!-- Chat Header (Toggle) -->
            <div class="chat-header" style="
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 10px 23px;
                cursor: pointer;
                user-select: none;
                transition: background 0.15s;
                min-height: 39.5px;
                box-sizing: border-box;
            ">
                <div style="
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 12px;
                    color: var(--gray-700);
                    font-weight: 600;
                    font-family: var(--font-stack);
                ">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                    <span style="letter-spacing: 0.02em;">JOB CHAT</span>
                    <span class="chat-count-badge" style="
                        background: var(--blue-100);
                        color: var(--blue-600);
                        padding: 2px 8px;
                        border-radius: 10px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: var(--font-stack);
                    ">0</span>
                    <span class="unread-indicator" style="
                        width: 8px;
                        height: 8px;
                        background: var(--red-500);
                        border-radius: 50%;
                        display: none;
                        animation: pulse-dot 2s infinite;
                    "></span>
                </div>
                <svg class="chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--gray-600)" stroke-width="2.5" style="
                    transition: transform 0.2s;
                ">
                    <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
            </div>

            <!-- Chat Body (Collapsible) -->
            <div class="chat-body" style="
                display: none;
                border-top: 1px solid var(--border-color);
                padding: 12px 23px 16px;
                background: var(--fg-color);
                font-family: var(--font-stack);
            ">
                <!-- Messages Container -->
                <div class="messages-container" style="
                    max-height: 280px;
                    overflow-y: auto;
                    margin-bottom: 12px;
                    padding: 4px;
                    scrollbar-width: thin;
                    scrollbar-color: var(--scrollbar-thumb-color) var(--scrollbar-track-color);
                ">
                    <div class="messages-list" style="
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                    ">
                        <div class="empty-state" style="
                            text-align: center;
                            color: var(--text-muted);
                            font-size: var(--text-sm);
                            padding: 20px 0;
                            font-family: var(--font-stack);
                        ">No messages yet. Start the conversation.</div>
                    </div>
                </div>

                <!-- Input Area -->
                <div class="chat-input-area" style="
                    display: flex;
                    gap: 8px;
                    align-items: flex-end;
                ">
                    <div style="flex: 1; position: relative;">
                        <textarea class="chat-input form-control" placeholder="Type your message..." rows="1" style="
                            resize: none;
                            border-radius: var(--border-radius-sm);
                            font-size: var(--text-md);
                            padding: var(--input-padding);
                            border: 1px solid var(--border-color);
                            min-height: 36px;
                            max-height: 80px;
                            font-family: var(--font-stack);
                            background: var(--control-bg);
                        "></textarea>
                    </div>
                    <button class="btn btn-primary btn-sm chat-send" style="
                        padding: 8px 16px;
                        border-radius: var(--border-radius-sm);
                        font-weight: var(--weight-semibold);
                        white-space: nowrap;
                        height: 36px;
                        font-family: var(--font-stack);
                        font-size: var(--text-sm);
                    ">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 4px;">
                            <line x1="22" y1="2" x2="11" y2="13"></line>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                        </svg>
                        Send
                    </button>
                </div>
            </div>
        </div>
    `);

    // Add pulse animation to CSS (only once)
    if (!$('style#chat-pulse-animation').length) {
        $('<style id="chat-pulse-animation">@keyframes pulse-dot { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(1.1); } }</style>')
            .appendTo('head');
    }

    // Append to grid row
    $row_wrapper.append($chat_section);

    // Load existing messages
    load_messages($chat_section, cdn);

    // ══════════════════════════════════════════════════════
    //  EVENT HANDLERS
    // ══════════════════════════════════════════════════════

    // Toggle chat on header click
    $chat_section.find('.chat-header').on('click', function() {
        let $body = $chat_section.find('.chat-body');
        let $chevron = $chat_section.find('.chevron');
        let is_open = $body.is(':visible');

        // CLOSE ALL OTHER CHATS FIRST
        frm.$wrapper.find('.job-chat-section').each(function() {
            if (this !== $chat_section[0]) {
                $(this).find('.chat-body').slideUp(200);
                $(this).find('.chevron').css('transform', 'rotate(0deg)');
                $(this).find('.chat-header').css('background', 'var(--gray-50)');
            }
        });

        if (is_open) {
            // Close this chat
            $body.slideUp(200);
            $chevron.css('transform', 'rotate(0deg)');
            $(this).css('background', 'var(--gray-50)');
        } else {
            // Open this chat
            $body.slideDown(200, function() {
                // Scroll to bottom
                let $container = $chat_section.find('.messages-container');
                $container.scrollTop($container[0].scrollHeight);
            });
            $chevron.css('transform', 'rotate(180deg)');
            $(this).css('background', 'var(--subtle-fg)');
            
            // Clear unread indicators
            clear_unread_indicators($chat_section);
            
            // ═══ CLEAR LIST VIEW NOTIFICATION ═══
            if (window.clear_task_chat_notification && frm.doc.name && cdn) {
                window.clear_task_chat_notification(frm.doc.name, cdn);
            }
        }
    });

    // Send message on button click
    $chat_section.find('.chat-send').on('click', function() {
        send_message(frm, $chat_section, cdn);
    });

    // Send on Enter (Shift+Enter = new line)
    $chat_section.find('.chat-input').on('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send_message(frm, $chat_section, cdn);
        }
    });

    // Auto-resize textarea
    $chat_section.find('.chat-input').on('input', function() {
        this.style.height = '36px';
        this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    // ══════════════════════════════════════════════════════
    //  REALTIME LISTENER
    // ══════════════════════════════════════════════════════
    frappe.realtime.on(`job_chat_${cdn}`, function(data) {
        // Only process if from someone else
        if (data.sent_by === frappe.session.user) return;

        // Append message bubble
        append_message_bubble($chat_section, data);

        // Increment count
        increment_message_count($chat_section);

        // Check if chat is open
        let is_open = $chat_section.find('.chat-body').is(':visible');
        
        if (is_open) {
            // Scroll to bottom if open
            let $container = $chat_section.find('.messages-container');
            $container.scrollTop($container[0].scrollHeight);
        } else {
            // Show unread indicator if closed
            show_unread_indicator($chat_section);
        }
    });
}

// ══════════════════════════════════════════════════════════
//  LOAD MESSAGES FROM DATABASE
// ══════════════════════════════════════════════════════════
function load_messages($chat_section, cdn) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Comment',
            filters: {
                reference_doctype: 'Task Job',
                reference_name: cdn,
                comment_type: 'Comment'
            },
            fields: ['name', 'content', 'owner', 'creation', 'comment_by'],
            order_by: 'creation asc',
            limit: 100
        },
        callback: function(r) {
            let messages = r.message || [];
            let $list = $chat_section.find('.messages-list');
            
            if (messages.length === 0) {
                update_message_count($chat_section, 0);
                return;
            }

            // Remove empty state
            $list.find('.empty-state').remove();

            // Render each message
            messages.forEach(msg => {
                append_message_bubble($chat_section, {
                    content: msg.content,
                    sent_by: msg.owner,
                    sender_name: msg.comment_by || msg.owner,
                    creation: msg.creation
                });
            });

            // Update count
            update_message_count($chat_section, messages.length);
        }
    });
}

// ══════════════════════════════════════════════════════════
//  SEND MESSAGE
// ══════════════════════════════════════════════════════════
function send_message(frm, $chat_section, cdn) {
    let $input = $chat_section.find('.chat-input');
    let message = $input.val().trim();
    
    if (!message) return;

    let $btn = $chat_section.find('.chat-send');
    $btn.prop('disabled', true).text('Sending...');

    // Determine role
    let role = frappe.user.has_role('Technician') ? 'Technician' : 'Support';

    frappe.call({
        method: 'frappe.client.insert',
        args: {
            doc: {
                doctype: 'Comment',
                comment_type: 'Comment',
                reference_doctype: 'Task Job',
                reference_name: cdn,
                content: message,
                comment_by: frappe.session.user_fullname || frappe.session.user
            }
        },
        callback: function(r) {
            $btn.prop('disabled', false).html(`
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 4px;">
                    <line x1="22" y1="2" x2="11" y2="13"></line>
                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                </svg>
                Send
            `);

            if (r.exc) {
                frappe.show_alert({ message: 'Failed to send message', indicator: 'red' });
                return;
            }

            // Clear input
            $input.val('').css('height', '36px');

            // Show message immediately
            let msg_data = {
                content: message,
                sent_by: frappe.session.user,
                sender_name: frappe.session.user_fullname || frappe.session.user,
                creation: frappe.datetime.now_datetime(),
                role: role
            };

            append_message_bubble($chat_section, msg_data);
            increment_message_count($chat_section);

            // Scroll to bottom
            let $container = $chat_section.find('.messages-container');
            $container.scrollTop($container[0].scrollHeight);

            // Broadcast to others via realtime
            frappe.call({
                method: 'fleet.api.chat.publish_job_chat',
                args: {
                    cdn: cdn,
                    message: message,
                    sender_name: msg_data.sender_name,
                    role: role
                }
            });
        }
    });
}

// ══════════════════════════════════════════════════════════
//  APPEND MESSAGE BUBBLE
// ══════════════════════════════════════════════════════════
function append_message_bubble($chat_section, data) {
    let $list = $chat_section.find('.messages-list');
    
    // Remove empty state if exists
    $list.find('.empty-state').remove();

    let is_mine = data.sent_by === frappe.session.user;
    let is_tech = data.role === 'Technician' || frappe.user.has_role('Technician');
    
    // Use Frappe CSS variables
    let avatar_bg = is_tech ? 'var(--blue-600)' : 'var(--green-600)';
    let bubble_bg = is_mine ? 'var(--blue-600)' : 'var(--control-bg)';
    let text_color = is_mine ? 'var(--neutral-white)' : 'var(--text-color)';
    let border = is_mine ? 'none' : '1px solid var(--border-color)';
    
    let initials = (data.sender_name || data.sent_by || '?')
        .split(' ')
        .map(w => w[0])
        .join('')
        .slice(0, 2)
        .toUpperCase();

    let time_str = data.creation 
        ? frappe.datetime.str_to_user(data.creation, true)
        : 'Just now';

    let $bubble = $(`
        <div style="
            display: flex;
            flex-direction: ${is_mine ? 'row-reverse' : 'row'};
            align-items: flex-start;
            gap: 8px;
            font-family: var(--font-stack);
        ">
            <!-- Avatar -->
            <div style="
                width: 28px;
                height: 28px;
                border-radius: 50%;
                background: ${avatar_bg};
                color: var(--neutral-white);
                font-size: 10px;
                font-weight: var(--weight-bold);
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                font-family: var(--font-stack);
            ">${initials}</div>

            <!-- Message Bubble -->
            <div style="max-width: 70%;">
                <div style="
                    font-size: var(--text-xs);
                    color: var(--text-muted);
                    margin-bottom: 3px;
                    text-align: ${is_mine ? 'right' : 'left'};
                    font-family: var(--font-stack);
                ">
                    ${!is_mine ? `<b style="color: var(--text-color)">${frappe.utils.escape_html(data.sender_name)}</b> · ` : ''}
                    <span>${time_str}</span>
                </div>
                <div style="
                    background: ${bubble_bg};
                    color: ${text_color};
                    padding: 8px 12px;
                    border-radius: ${is_mine ? '12px 12px 2px 12px' : '12px 12px 12px 2px'};
                    font-size: var(--text-md);
                    line-height: 1.5;
                    word-break: break-word;
                    border: ${border};
                    box-shadow: var(--shadow-sm);
                    font-family: var(--font-stack);
                    letter-spacing: 0.02em;
                ">${frappe.utils.escape_html(data.content)}</div>
            </div>
        </div>
    `);

    $list.append($bubble);
}

// ══════════════════════════════════════════════════════════
//  MESSAGE COUNT MANAGEMENT
// ══════════════════════════════════════════════════════════
function update_message_count($chat_section, count) {
    $chat_section.find('.chat-count-badge').text(count);
    if (count > 0) {
        $chat_section.find('.chat-count-badge').show();
    } else {
        $chat_section.find('.chat-count-badge').hide();
    }
}

function increment_message_count($chat_section) {
    let $badge = $chat_section.find('.chat-count-badge');
    let current = parseInt($badge.text() || '0');
    $badge.text(current + 1).show();
}

// ══════════════════════════════════════════════════════════
//  UNREAD INDICATORS
// ══════════════════════════════════════════════════════════
function show_unread_indicator($chat_section) {
    $chat_section.find('.unread-indicator').show();
    $chat_section.find('.chat-header').css('background', 'var(--subtle-fg)');
}

function clear_unread_indicators($chat_section) {
    $chat_section.find('.unread-indicator').hide();
    $chat_section.find('.chat-header').css('background', 'var(--gray-50)');
}