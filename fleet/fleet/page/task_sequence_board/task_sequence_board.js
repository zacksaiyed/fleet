frappe.pages["task-sequence-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "",
		single_column: true,
	});

	$(wrapper).find(".page-head").hide();
	$(wrapper).addClass("tsb-full-width-page");

	$(wrapper)
		.find(".container, .layout-main-section-wrapper")
		.css({
			width: "100%",
			maxWidth: "100%",
		});

	const $main = $(wrapper).find(".layout-main-section");

	$main.css({
		width: "100%",
		maxWidth: "100%",
	});

	$main.empty();

	let technician_control = null;
	let is_saving = false;
	let load_request_id = 0;
	let board_data = [];

	const technician_tabs = {};


	// =========================================================
	// HTML
	// =========================================================

	$main.html(`
		<div class="tsb-page">

			<div class="tsb-header">

				<div class="tsb-title-section">

					<div class="tsb-title-icon">
						<svg
							width="20"
							height="20"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<rect
								x="5"
								y="4"
								width="14"
								height="16"
								rx="2"
							></rect>

							<path d="M9 4V2"></path>
							<path d="M15 4V2"></path>
							<path d="M8 9h8"></path>
							<path d="M8 13h5"></path>
						</svg>
					</div>

					<div>
						<div class="tsb-title">
							Task Activity
						</div>

						<div class="tsb-subtitle">
							Drag and drop pending tasks to set the sequence for each technician
						</div>
					</div>

				</div>


				<div class="tsb-actions">

					<div class="tsb-filter-box">
						<div
							id="tsb-technician-filter"
							class="tsb-technician-filter"
						></div>
					</div>


					<button
						type="button"
						class="btn tsb-new-task-btn"
					>
						<span class="tsb-plus">+</span>
						<span>New Task</span>
					</button>


					<button
						type="button"
						class="btn tsb-refresh-btn"
					>
						<span class="tsb-refresh-symbol">↻</span>
						<span>Refresh</span>
					</button>

				</div>

			</div>


			<div class="tsb-board-wrapper">
				<div class="tsb-board"></div>
			</div>

		</div>
	`);


	// =========================================================
	// CSS
	// =========================================================

	$("#task-sequence-board-custom-style").remove();

	$(`
		<style id="task-sequence-board-custom-style">

			.tsb-full-width-page .container,
			.tsb-full-width-page .layout-main-section-wrapper,
			.tsb-full-width-page .layout-main-section {
				width: 100% !important;
				max-width: 100% !important;
			}

			.tsb-full-width-page .layout-main-section {
				padding-left: 0 !important;
				padding-right: 0 !important;
			}


			/* PAGE */

			.tsb-page {
				width: 95%;
				max-width: none;
				margin: 0 auto;
				padding: 28px 0 60px;

				font-family:
					Inter,
					-apple-system,
					BlinkMacSystemFont,
					"Segoe UI",
					sans-serif;
			}


			/* HEADER */

			.tsb-header {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 20px;
				margin-bottom: 20px;
			}

			.tsb-title-section {
				display: flex;
				align-items: center;
				gap: 12px;
				min-width: 0;
			}

			.tsb-title-icon {
				width: 44px;
				height: 44px;
				min-width: 44px;

				display: flex;
				align-items: center;
				justify-content: center;

				border-radius: 12px;

				color: #ffffff;

				background:
					linear-gradient(
						135deg,
						#6675ff,
						#5364f5
					);

				box-shadow:
					0 8px 20px
					rgba(83, 100, 245, 0.22);
			}

			.tsb-title {
				font-size: 22px;
				font-weight: 750;
				line-height: 1.2;
				color: #111827;
			}

			.tsb-subtitle {
				margin-top: 4px;
				font-size: 12px;
				color: #718096;
			}


			/* ACTIONS */

			.tsb-actions {
				display: flex;
				align-items: center;
				justify-content: flex-end;
				gap: 10px;
			}


			/* FILTER */

			.tsb-filter-box {
				width: 320px;
				min-width: 260px;
			}

			.tsb-technician-filter {
				width: 100%;
			}

			.tsb-technician-filter .frappe-control,
			.tsb-technician-filter .form-group {
				margin: 0 !important;
			}

			.tsb-technician-filter .control-label,
			.tsb-technician-filter .help-box {
				display: none !important;
			}

			.tsb-technician-filter .control-input-wrapper {
				margin: 0 !important;
			}

			.tsb-technician-filter .form-control {
				min-height: 38px !important;
				border: 1px solid #dfe5ee !important;
				border-radius: 9px !important;
				background: #f8fafc !important;
				box-shadow: none !important;
				font-size: 12px !important;
			}

			.tsb-technician-filter .form-control:focus {
				background: #ffffff !important;
				border-color: #6675ff !important;

				box-shadow:
					0 0 0 3px
					rgba(83, 100, 245, 0.08)
					!important;
			}


			/* BUTTONS */

			.tsb-new-task-btn,
			.tsb-refresh-btn {
				height: 38px;

				display: inline-flex !important;
				align-items: center;
				justify-content: center;

				gap: 7px;

				padding: 0 16px !important;

				border: none !important;
				border-radius: 9px !important;

				font-size: 12px !important;
				font-weight: 650 !important;

				transition:
					transform 0.18s ease,
					box-shadow 0.18s ease;
			}

			.tsb-new-task-btn {
				background: #5364f5 !important;
				color: #ffffff !important;

				box-shadow:
					0 5px 14px
					rgba(83, 100, 245, 0.18);
			}

			.tsb-new-task-btn:hover {
				transform: translateY(-1px);

				box-shadow:
					0 8px 18px
					rgba(83, 100, 245, 0.25);
			}

			.tsb-refresh-btn {
				background: #172033 !important;
				color: #ffffff !important;
			}

			.tsb-refresh-btn:hover {
				transform: translateY(-1px);

				box-shadow:
					0 8px 18px
					rgba(15, 23, 42, 0.18);
			}

			.tsb-plus {
				font-size: 18px;
				font-weight: 400;
				line-height: 1;
			}

			.tsb-refresh-symbol {
				font-size: 17px;
				line-height: 1;
			}


			/* BOARD */

			.tsb-board-wrapper {
				width: 100%;

				overflow-x: auto;
				overflow-y: visible;

				padding: 2px 2px 16px;

				scrollbar-width: thin;
				scrollbar-color: #cbd5e1 transparent;
			}

			.tsb-board-wrapper::-webkit-scrollbar {
				height: 8px;
			}

			.tsb-board-wrapper::-webkit-scrollbar-track {
				background: transparent;
			}

			.tsb-board-wrapper::-webkit-scrollbar-thumb {
				background: #cbd5e1;
				border-radius: 20px;
			}

			.tsb-board {
				display: flex;
				flex-direction: row;
				flex-wrap: nowrap;
				align-items: flex-start;

				gap: 14px;

				width: max-content;
				min-width: 100%;
			}


			/* TECHNICIAN */

			.tsb-technician {
				flex: 0 0 320px;

				width: 320px;
				min-width: 320px;
				max-width: 320px;

				padding: 14px 14px 16px;

				border: 1px solid #dce4ee;
				border-radius: 16px;

				background: #ffffff;

				box-shadow:
					0 6px 24px
					rgba(15, 23, 42, 0.035);

				transition:
					border-color 0.2s ease,
					box-shadow 0.2s ease;
			}

			.tsb-technician:hover {
				border-color: #cdd8e7;

				box-shadow:
					0 10px 30px
					rgba(15, 23, 42, 0.055);
			}


			/* TECHNICIAN HEADER */

			.tsb-technician-header {
				display: flex;
				align-items: center;

				gap: 11px;

				margin-bottom: 12px;

				padding: 0 2px;
			}

			.tsb-avatar {
				width: 42px;
				height: 42px;
				min-width: 42px;

				display: flex;
				align-items: center;
				justify-content: center;

				border-radius: 12px;

				font-size: 16px;
				font-weight: 750;

				overflow: hidden;
			}

			.tsb-avatar-image {
				width: 100%;
				height: 100%;

				display: block;

				object-fit: cover;

				border-radius: 12px;
			}

			.tsb-avatar-0 {
				background: #dff1ff;
				color: #1570b8;
			}

			.tsb-avatar-1 {
				background: #ffe0ef;
				color: #d92678;
			}

			.tsb-avatar-2 {
				background: #dcf7eb;
				color: #07895e;
			}

			.tsb-avatar-3 {
				background: #eee7ff;
				color: #7048d8;
			}

			.tsb-avatar-4 {
				background: #fff0d7;
				color: #c56a0b;
			}

			.tsb-tech-info {
				min-width: 0;
			}

			.tsb-tech-name {
				font-size: 14px;
				font-weight: 720;
				line-height: 1.2;

				color: #111827;

				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}

			.tsb-tech-id {
				margin-top: 4px;

				font-size: 11px;

				color: #718096;

				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}


			/* TABS */

			.tsb-tech-tabs {
				display: flex;
				align-items: center;

				gap: 5px;

				margin: 4px 0 13px;

				padding: 4px;

				border: 1px solid #e2e8f0;
				border-radius: 10px;

				background: #f8fafc;
			}

			.tsb-tech-tab {
				flex: 1;

				height: 34px;

				display: flex;
				align-items: center;
				justify-content: center;

				padding: 0 8px;

				border: none;
				border-radius: 7px;

				background: transparent;

				color: #64748b;

				font-size: 11px;
				font-weight: 700;

				cursor: pointer;

				transition:
					background 0.15s ease,
					color 0.15s ease,
					box-shadow 0.15s ease;
			}

			.tsb-tech-tab:hover {
				background: #ffffff;
				color: #334155;
			}

			.tsb-tech-tab.active {
				background: #ffffff;

				box-shadow:
					0 2px 7px
					rgba(15, 23, 42, 0.08);
			}

			.tsb-tech-tab.active[data-tab="pending"] {
				color: #b56b00;
			}

			.tsb-tech-tab.active[data-tab="completed"] {
				color: #078b52;
			}


			/* TASK ROW */

			.tsb-task-row {
				display: flex;
				flex-direction: column;

				gap: 10px;

				min-height: 90px;

				padding: 3px;

				overflow: visible;
			}


			/* TASK CARD */

			.tsb-task-card {
				position: relative;

				width: 100%;
				min-width: 0;

				min-height: 92px;

				padding: 15px;

				border: 1px solid;
				border-radius: 13px;

				user-select: none;

				overflow: hidden;

				transition:
					transform 0.2s ease,
					box-shadow 0.2s ease,
					filter 0.2s ease;
			}

			.tsb-task-card[data-active-task="1"] {
				cursor: grab;
			}

			.tsb-task-card[data-active-task="1"]:active {
				cursor: grabbing;
			}

			.tsb-completed-card {
				cursor: default;
			}

			.tsb-task-card::before {
				content: "";

				position: absolute;

				left: -1px;
				top: 22px;

				width: 5px;
				height: 40px;

				border-radius: 0 6px 6px 0;

				background: var(--accent);
			}

			.tsb-task-card::after {
				content: "";

				position: absolute;

				right: -42px;
				bottom: -55px;

				width: 100px;
				height: 100px;

				border-radius: 50%;

				background:
					rgba(255, 255, 255, 0.28);

				pointer-events: none;
			}

			.tsb-task-card:hover {
				transform: translateY(-3px);

				box-shadow:
					0 12px 24px
					rgba(15, 23, 42, 0.10);

				filter: saturate(1.05);

				z-index: 3;
			}


			/* TASK TOP ROW */

			.tsb-task-top {
				position: relative;
				z-index: 2;

				display: flex;
				align-items: flex-start;
				justify-content: space-between;

				gap: 10px;

				width: 100%;
			}

			.tsb-task-title {
				flex: 1;

				min-width: 0;

				padding-top: 3px;

				font-size: 12px;
				font-weight: 720;
				line-height: 1.35;

				color: #111827;

				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}


			/* STATUS */

			.tsb-status {
				flex: 0 0 auto;

				height: 25px;

				display: inline-flex;
				align-items: center;

				gap: 6px;

				padding: 0 9px;

				border-radius: 20px;

				font-size: 9px;
				font-weight: 700;

				white-space: nowrap;
			}

			.tsb-status-dot {
				width: 6px;
				height: 6px;

				border-radius: 50%;

				background: currentColor;
			}

			.tsb-status-open {
				color: #7356d9;
				background: #eee8ff;
			}

			.tsb-status-in-progress,
			.tsb-status-working {
				color: #0875d1;
				background: #dcecff;
			}

			.tsb-status-accepted {
				color: #078d8c;
				background: #d6f5f2;
			}

			.tsb-status-pending,
			.tsb-status-pending-review {
				color: #b56b00;
				background: #fff0c7;
			}

			.tsb-status-on-hold,
			.tsb-status-overdue {
				color: #c82045;
				background: #ffdce4;
			}

			.tsb-status-completed {
				color: #078b52;
				background: #d8f7e8;
			}

			.tsb-status-rejected,
			.tsb-status-cancelled,
			.tsb-status-default {
				color: #607089;
				background: #e5ebf3;
			}


			/* TASK BOTTOM ROW */

			.tsb-task-bottom {
				position: relative;
				z-index: 5;

				display: flex;
				align-items: center;
				justify-content: space-between;

				gap: 10px;

				margin-top: 18px;
			}

			.tsb-task-id {
				min-width: 0;

				font-size: 10px;
				font-weight: 650;

				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}

			.tsb-task-id-link {
				color: #5364f5;

				text-decoration: none;

				cursor: pointer;
			}

			.tsb-task-id-link:hover {
				color: #3f51dc;

				text-decoration: underline;
			}


			/* JOB COUNT */

			.tsb-job-count {
				flex: 0 0 auto;

				display: inline-flex;
				align-items: center;

				gap: 5px;

				padding: 4px 7px;

				border-radius: 7px;

				background:
					rgba(255, 255, 255, 0.72);

				border:
					1px solid
					rgba(148, 163, 184, 0.20);

				color: #64748b;

				font-size: 9px;
				font-weight: 700;
			}

			.tsb-job-count svg {
				width: 13px;
				height: 13px;

				stroke-width: 2;
			}


			/* DRAG */

			.tsb-dragging-card {
				opacity: 0.35;
			}

			.tsb-chosen-card {
				box-shadow:
					0 15px 32px
					rgba(15, 23, 42, 0.15);
			}

			.tsb-moving-card {
				transform: rotate(1deg);
			}


			/* CARD COLORS */

			.tsb-color-blue {
				--accent: #4383f5;

				background:
					linear-gradient(
						135deg,
						#f0f6ff,
						#e7f1ff
					);

				border-color: #bfd7ff;
			}

			.tsb-color-green {
				--accent: #16b89b;

				background:
					linear-gradient(
						135deg,
						#effcf8,
						#ddf8f1
					);

				border-color: #b9eadc;
			}

			.tsb-color-red {
				--accent: #f34d6b;

				background:
					linear-gradient(
						135deg,
						#fff1f4,
						#ffe4ea
					);

				border-color: #ffc4cf;
			}

			.tsb-color-purple {
				--accent: #8a63e8;

				background:
					linear-gradient(
						135deg,
						#f7f3ff,
						#eee6ff
					);

				border-color: #ddceff;
			}

			.tsb-color-yellow {
				--accent: #e9a521;

				background:
					linear-gradient(
						135deg,
						#fffaf0,
						#fff2d7
					);

				border-color: #f6d99d;
			}

			.tsb-color-grey {
				--accent: #8c9bb0;

				background:
					linear-gradient(
						135deg,
						#f7f9fc,
						#edf2f7
					);

				border-color: #d8e0ea;
			}


			/* EMPTY */

			.tsb-no-task {
				min-height: 92px;

				display: flex;
				align-items: center;
				justify-content: center;

				width: 100%;

				border: 1px dashed #dce4ee;
				border-radius: 12px;

				background: #fafcff;

				font-size: 11px;

				color: #94a3b8;
			}

			.tsb-empty {
				width: 100%;
				min-width: 500px;

				padding: 55px 20px;

				text-align: center;

				border: 1px dashed #dce4ee;
				border-radius: 14px;

				background: #fafcff;

				font-size: 13px;

				color: #718096;
			}


			/* LOADING */

			.tsb-loading {
				width: 100%;
				min-width: 500px;

				padding: 60px 20px;

				display: flex;
				flex-direction: column;
				align-items: center;
				justify-content: center;

				gap: 12px;

				font-size: 12px;

				color: #718096;
			}

			.tsb-spinner {
				width: 25px;
				height: 25px;

				border: 3px solid #e5e7eb;
				border-top-color: #5364f5;

				border-radius: 50%;

				animation:
					tsb-spin
					0.7s
					linear
					infinite;
			}

			@keyframes tsb-spin {
				to {
					transform: rotate(360deg);
				}
			}


			/* RESPONSIVE */

			@media (max-width: 1100px) {
				.tsb-page {
					width: 94%;
				}

				.tsb-technician {
					flex: 0 0 300px;

					width: 300px;
					min-width: 300px;
					max-width: 300px;
				}
			}

			@media (max-width: 900px) {
				.tsb-page {
					width: 92%;
				}

				.tsb-header {
					flex-direction: column;
					align-items: flex-start;
				}

				.tsb-actions {
					width: 100%;
					flex-wrap: wrap;
					justify-content: flex-start;
				}

				.tsb-filter-box {
					width: 100%;
				}

				.tsb-technician {
					flex: 0 0 285px;

					width: 285px;
					min-width: 285px;
					max-width: 285px;
				}
			}

		</style>
	`).appendTo("head");


	// =========================================================
	// HELPERS
	// =========================================================

	function escape_html(value) {
		if (value === null || value === undefined) {
			return "";
		}

		return $("<div>")
			.text(String(value))
			.html();
	}


	function escape_attribute(value) {
		return escape_html(value);
	}


	function get_initial(name) {
		const value = String(name || "").trim();

		if (!value) {
			return "?";
		}

		return value.charAt(0).toUpperCase();
	}


	function normalize_status(status) {
		return String(status || "")
			.trim()
			.toLowerCase()
			.replace(/_/g, "-")
			.replace(/\s+/g, "-");
	}


	function get_status_class(status) {
		const value = normalize_status(status);

		const supported = [
			"open",
			"in-progress",
			"working",
			"accepted",
			"pending",
			"pending-review",
			"on-hold",
			"overdue",
			"completed",
			"rejected",
			"cancelled",
		];

		if (supported.includes(value)) {
			return `tsb-status-${value}`;
		}

		return "tsb-status-default";
	}


	function get_card_color(status) {
		const value = normalize_status(status);

		if (
			value === "in-progress" ||
			value === "working"
		) {
			return "tsb-color-blue";
		}

		if (
			value === "accepted" ||
			value === "completed"
		) {
			return "tsb-color-green";
		}

		if (
			value === "on-hold" ||
			value === "overdue"
		) {
			return "tsb-color-red";
		}

		if (
			value === "pending" ||
			value === "pending-review"
		) {
			return "tsb-color-yellow";
		}

		if (value === "open") {
			return "tsb-color-purple";
		}

		return "tsb-color-grey";
	}


	function get_job_count(task) {
		if (
			task.job_count !== undefined &&
			task.job_count !== null
		) {
			return Number(task.job_count) || 0;
		}

		if (Array.isArray(task.custom_task_jobs)) {
			return task.custom_task_jobs.length;
		}

		return 0;
	}


	function get_employee_image(data) {
		return (
			data.image ||
			data.employee_image ||
			data.custom_image ||
			""
		);
	}


	function get_avatar_html(data, index) {
		const employee_name =
			data.employee_name ||
			data.employee ||
			"";

		const image =
			get_employee_image(data);

		if (image) {
			return `
				<div
					class="
						tsb-avatar
						tsb-avatar-${index % 5}
					"
				>
					<img
						src="${escape_attribute(image)}"
						alt="${escape_attribute(employee_name)}"
						class="tsb-avatar-image"
						onerror="
							this.style.display='none';
							this.parentElement.querySelector('.tsb-avatar-fallback').style.display='flex';
						"
					>

					<span
						class="tsb-avatar-fallback"
						style="
							display:none;
							width:100%;
							height:100%;
							align-items:center;
							justify-content:center;
						"
					>
						${escape_html(get_initial(employee_name))}
					</span>
				</div>
			`;
		}

		return `
			<div
				class="
					tsb-avatar
					tsb-avatar-${index % 5}
				"
			>
				${escape_html(get_initial(employee_name))}
			</div>
		`;
	}


	function get_job_icon() {
		return `
			<svg
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-linecap="round"
				stroke-linejoin="round"
				aria-hidden="true"
			>
				<circle
					cx="12"
					cy="7"
					r="4"
				></circle>

				<path
					d="M5.5 21v-2a6.5 6.5 0 0 1 13 0v2"
				></path>

				<path
					d="M9 14.2V17l3 2 3-2v-2.8"
				></path>
			</svg>
		`;
	}


	// =========================================================
	// TASK CARD
	// =========================================================

	function get_task_card(
		task,
		completed = false
	) {
		const status =
			task.status ||
			(
				completed
					? "Completed"
					: "Open"
			);

		const status_class =
			get_status_class(status);

		const card_color =
			get_card_color(status);

		const title =
			task.subject ||
			task.name ||
			"";

		const job_count =
			get_job_count(task);

		return `
			<div
				class="
					tsb-task-card
					${card_color}
					${completed ? "tsb-completed-card" : ""}
				"
				data-task="${escape_attribute(task.name)}"
				${completed ? "" : 'data-active-task="1"'}
			>

				<div class="tsb-task-top">

					<div
						class="tsb-task-title"
						title="${escape_attribute(title)}"
					>
						${escape_html(title)}
					</div>


					<div
						class="
							tsb-status
							${status_class}
						"
					>
						<span class="tsb-status-dot"></span>

						<span>
							${escape_html(status)}
						</span>
					</div>

				</div>


				<div class="tsb-task-bottom">

					<div class="tsb-task-id">

						<a
							href="#"
							class="tsb-task-id-link"
							data-task="${escape_attribute(task.name)}"
						>
							${escape_html(task.name)}
						</a>

					</div>


					<div
						class="tsb-job-count"
						title="${job_count} Job${job_count === 1 ? "" : "s"}"
					>
						${get_job_icon()}

						<span>
							${job_count}
						</span>
					</div>

				</div>

			</div>
		`;
	}


	// =========================================================
	// SORT TASKS
	// =========================================================

	function sort_pending_tasks(tasks) {
		return [...tasks].sort(
			(a, b) =>
				(
					(Number(b.custom_sequence) || 0) -
					(Number(a.custom_sequence) || 0)
				) ||
				(
					new Date(b.creation || 0) -
					new Date(a.creation || 0)
				)
		);
	}


	function sort_completed_tasks(tasks) {
		return [...tasks].sort(
			(a, b) =>
				new Date(
					b.completed_on ||
					b.modified ||
					b.creation ||
					0
				) -
				new Date(
					a.completed_on ||
					a.modified ||
					a.creation ||
					0
				)
		);
	}


	// =========================================================
	// TECHNICIAN
	// =========================================================

	function render_technician(data, index) {
		const employee =
			data.employee || "";

		const employee_name =
			data.employee_name ||
			employee;

		const pending_tasks =
			sort_pending_tasks(
				Array.isArray(data.tasks)
					? data.tasks
					: []
			);

		const completed_tasks =
			sort_completed_tasks(
				Array.isArray(data.completed_tasks)
					? data.completed_tasks
					: []
			);

		const selected_tab =
			technician_tabs[employee] ||
			"pending";

		const visible_tasks =
			selected_tab === "completed"
				? completed_tasks
				: pending_tasks;

		const tasks_html =
			visible_tasks.length
				? visible_tasks
					.map(
						(task) =>
							get_task_card(
								task,
								selected_tab === "completed"
							)
					)
					.join("")
				: `
					<div class="tsb-no-task">
						${selected_tab === "completed"
					? "No completed tasks"
					: "No pending tasks"
				}
					</div>
				`;

		return `
			<div
				class="tsb-technician"
				data-employee="${escape_attribute(employee)}"
			>

				<div class="tsb-technician-header">

					${get_avatar_html(data, index)}

					<div class="tsb-tech-info">

						<div
							class="tsb-tech-name"
							title="${escape_attribute(employee_name)}"
						>
							${escape_html(employee_name)}
						</div>

					</div>

				</div>


				<div class="tsb-tech-tabs">

    <button
        type="button"
        class="
            tsb-tech-tab
            ${selected_tab === "pending" ? "active" : ""}
        "
        data-tab="pending"
        data-employee="${escape_attribute(employee)}"
    >
        Pending (${pending_tasks.length})
    </button>

    <button
        type="button"
        class="
            tsb-tech-tab
            ${selected_tab === "completed" ? "active" : ""}
        "
        data-tab="completed"
        data-employee="${escape_attribute(employee)}"
    >
        Completed (${completed_tasks.length})
    </button>

</div>


				<div
					class="tsb-task-row"
					data-employee="${escape_attribute(employee)}"
					data-tab="${escape_attribute(selected_tab)}"
				>
					${tasks_html}
				</div>

			</div>
		`;
	}


	// =========================================================
	// RENDER BOARD
	// =========================================================

	function render_board(data) {
		const $board =
			$main.find(".tsb-board");

		board_data =
			Array.isArray(data)
				? data
				: [];

		if (!board_data.length) {
			$board.html(`
				<div class="tsb-empty">
					No tasks found for the selected technician.
				</div>
			`);

			return;
		}

		const html =
			board_data
				.map(
					(row, index) =>
						render_technician(
							row,
							index
						)
				)
				.join("");

		$board.html(html);

		setup_technician_tabs();
		setup_task_click();
		setup_drag_drop();
	}


	// =========================================================
	// RENDER ONE TECHNICIAN
	// =========================================================

	function rerender_technician(employee) {
		const index =
			board_data.findIndex(
				(row) =>
					String(row.employee || "") ===
					String(employee || "")
			);

		if (index === -1) {
			return;
		}

		const data =
			board_data[index];

		const $old =
			$main
				.find(".tsb-technician")
				.filter(function () {
					return (
						String(
							$(this).attr("data-employee") || ""
						) ===
						String(employee || "")
					);
				})
				.first();

		if (!$old.length) {
			render_board(board_data);
			return;
		}

		const html =
			render_technician(
				data,
				index
			);

		$old.replaceWith(html);

		setup_technician_tabs();
		setup_task_click();
		setup_drag_drop();
	}


	// =========================================================
	// TECHNICIAN TABS
	// =========================================================

	function setup_technician_tabs() {
		$main
			.find(".tsb-tech-tab")
			.off("click.tsb")
			.on(
				"click.tsb",
				function () {
					const employee =
						$(this).attr("data-employee");

					const tab =
						$(this).attr("data-tab");

					if (!employee || !tab) {
						return;
					}

					const current =
						technician_tabs[employee] ||
						"pending";

					if (current === tab) {
						return;
					}

					technician_tabs[employee] =
						tab;

					rerender_technician(
						employee
					);
				}
			);
	}


	// =========================================================
	// TASK CLICK
	// =========================================================

	function setup_task_click() {
		$main
			.find(".tsb-task-id-link")
			.off("click.tsb")
			.on(
				"click.tsb",
				function (e) {
					e.preventDefault();
					e.stopPropagation();

					const task =
						$(this).attr(
							"data-task"
						);

					if (!task) {
						return;
					}

					const url =
						frappe.utils.get_form_link(
							"Task",
							task
						);

					window.open(
						url,
						"_blank"
					);
				}
			);
	}


	// =========================================================
	// GET TASK ORDER
	// =========================================================

	function get_task_order($row) {
		const tasks = [];

		$row
			.children(".tsb-task-card")
			.each(function () {
				const task =
					$(this).attr(
						"data-task"
					);

				if (task) {
					tasks.push(task);
				}
			});

		return tasks;
	}


	// =========================================================
	// SAVE SEQUENCE
	// =========================================================

	function save_sequence(
		employee,
		task_names,
		source_employee = null
	) {
		if (is_saving) {
			return;
		}

		is_saving = true;

		frappe.call({
			method:
				"fleet.fleet.page.task_sequence_board.task_sequence_board.update_task_sequence",

			args: {
				employee:
					employee,

				tasks:
					JSON.stringify(
						task_names
					),

				source_employee:
					source_employee,
			},

			callback(r) {
				is_saving = false;

				if (
					r.message &&
					r.message.status === "success"
				) {
					frappe.show_alert({
						message:
							__(
								"Task sequence updated"
							),

						indicator:
							"green",
					});
				} else {
					frappe.msgprint(
						__(
							"Unable to update task sequence"
						)
					);
				}

				load_board(
					get_selected_technicians()
				);
			},

			error() {
				is_saving = false;

				frappe.msgprint(
					__(
						"Unable to update task sequence"
					)
				);

				load_board(
					get_selected_technicians()
				);
			},
		});
	}


	// =========================================================
	// DRAG & DROP
	// =========================================================

	function setup_drag_drop() {
		$main
			.find(
				'.tsb-task-row[data-tab="pending"]'
			)
			.each(function () {
				const element =
					this;

				if (
					element._task_sequence_sortable
				) {
					element
						._task_sequence_sortable
						.destroy();
				}

				element._task_sequence_sortable =
					new Sortable(
						element,
						{
							group:
								"technician-task-board",

							animation:
								180,

							draggable:
								".tsb-task-card[data-active-task='1']",

							filter:
								".tsb-task-id-link",

							preventOnFilter:
								false,

							ghostClass:
								"tsb-dragging-card",

							chosenClass:
								"tsb-chosen-card",

							dragClass:
								"tsb-moving-card",

							onEnd(evt) {
								if (is_saving) {
									load_board(
										get_selected_technicians()
									);

									return;
								}

								if (
									evt.from === evt.to &&
									evt.oldIndex === evt.newIndex
								) {
									return;
								}

								const $source =
									$(evt.from);

								const $target =
									$(evt.to);

								$source
									.children(".tsb-no-task")
									.remove();

								$target
									.children(".tsb-no-task")
									.remove();

								save_sequence(
									$target.attr(
										"data-employee"
									),

									get_task_order(
										$target
									),

									$source.attr(
										"data-employee"
									)
								);
							},
						}
					);
			});
	}


	// =========================================================
	// TECHNICIAN FILTER
	// =========================================================

	function setup_technician_filter() {
		const $filter =
			$main.find(
				"#tsb-technician-filter"
			);

		$filter.empty();

		technician_control =
			frappe.ui.form.make_control({
				parent:
					$filter,

				df: {
					fieldtype:
						"MultiSelectList",

					fieldname:
						"technicians",

					label:
						__(
							"Technician"
						),

					placeholder:
						__(
							"Select Technician"
						),

					get_data(txt) {
						return frappe.db
							.get_link_options(
								"Employee",
								txt || "",
								{
									designation:
										"Technician",

									status:
										"Active",
								}
							);
					},

					change() {
						load_board(
							get_selected_technicians()
						);
					},
				},

				render_input:
					true,
			});

		technician_control.refresh();
	}


	// =========================================================
	// SELECTED TECHNICIANS
	// =========================================================

	function get_selected_technicians() {
		if (!technician_control) {
			return [];
		}

		let technicians =
			technician_control.get_value() ||
			[];

		if (!Array.isArray(technicians)) {
			technicians =
				technicians
					? [technicians]
					: [];
		}

		return technicians.filter(Boolean);
	}


	// =========================================================
	// LOAD BOARD
	// =========================================================

	function load_board(
		technicians = []
	) {
		const $board =
			$main.find(
				".tsb-board"
			);

		if (!Array.isArray(technicians)) {
			technicians =
				technicians
					? [technicians]
					: [];
		}

		const request_id =
			++load_request_id;

		$board.html(`
			<div class="tsb-loading">

				<div class="tsb-spinner"></div>

				<div>
					Loading tasks...
				</div>

			</div>
		`);

		frappe.call({
			method:
				"fleet.fleet.page.task_sequence_board.task_sequence_board.get_task_sequence_board",

			args: {
				technicians:
					JSON.stringify(
						technicians
					),
			},

			callback(r) {
				if (
					request_id !==
					load_request_id
				) {
					return;
				}

				render_board(
					r.message ||
					[]
				);
			},

			error() {
				if (
					request_id !==
					load_request_id
				) {
					return;
				}

				$board.html(`
					<div class="tsb-empty">
						Unable to load Task Sequence Board.
					</div>
				`);
			},
		});
	}


	// =========================================================
	// REFRESH
	// =========================================================

	function refresh_board() {
		load_board(
			get_selected_technicians()
		);
	}


	// =========================================================
	// NEW TASK
	// =========================================================

	$main
		.find(".tsb-new-task-btn")
		.off("click.tsb")
		.on(
			"click.tsb",
			function () {
				const url =
					frappe.utils.get_form_link(
						"Task",
						"new-task-1"
					);

				window.open(
					url,
					"_blank"
				);
			}
		);


	// =========================================================
	// REFRESH BUTTON
	// =========================================================

	$main
		.find(".tsb-refresh-btn")
		.off("click.tsb")
		.on(
			"click.tsb",
			function () {
				refresh_board();
			}
		);


	// =========================================================
	// INITIALIZE
	// =========================================================

	setup_technician_filter();

	load_board([]);
};