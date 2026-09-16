frappe.pages["task-sequence-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "",
		single_column: true,
	});

	$(wrapper).find(".page-head").hide();

	const $main = $(wrapper).find(".layout-main-section");
	$main.empty();

	let technician_control = null;
	let is_saving = false;

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
							Drag and drop tasks to set the sequence for each technician
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


			<div class="tsb-board"></div>

		</div>
	`);


	// =========================================================
	// CSS
	// =========================================================

	$("#task-sequence-board-custom-style").remove();

	$(`
		<style id="task-sequence-board-custom-style">

			/* =================================================
			   PAGE
			================================================= */

			.tsb-page {
				width: 100%;
				max-width: 1500px;
				margin: 0 auto;
				padding: 30px 20px 60px;
				font-family:
					Inter,
					-apple-system,
					BlinkMacSystemFont,
					"Segoe UI",
					sans-serif;
			}


			/* =================================================
			   HEADER
			================================================= */

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


			/* =================================================
			   ACTIONS
			================================================= */

			.tsb-actions {
				display: flex;
				align-items: center;
				justify-content: flex-end;
				gap: 10px;
			}


			/* =================================================
			   MULTI SELECT
			================================================= */

			.tsb-filter-box {
				width: 320px;
				min-width: 260px;
			}

			.tsb-technician-filter {
				width: 100%;
			}

			.tsb-technician-filter .frappe-control {
				margin: 0 !important;
			}

			.tsb-technician-filter .form-group {
				margin: 0 !important;
			}

			.tsb-technician-filter .control-label {
				display: none !important;
			}

			.tsb-technician-filter .help-box {
				display: none !important;
			}

			.tsb-technician-filter .control-input-wrapper {
				margin: 0 !important;
			}

			.tsb-technician-filter .form-control {
				min-height: 38px !important;

				border:
					1px solid #dfe5ee !important;

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


			/* =================================================
			   BUTTONS
			================================================= */

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


			/* =================================================
			   TECHNICIAN
			================================================= */

			.tsb-technician {
				margin-bottom: 18px;

				padding:
					14px
					14px
					12px;

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


			/* =================================================
			   TECHNICIAN HEADER
			================================================= */

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
			}

			.tsb-tech-id {
				margin-top: 4px;

				font-size: 11px;

				color: #718096;
			}


			/* =================================================
			   TASK ROW
			================================================= */

			.tsb-task-row,
			.tsb-completed-row {
				display: flex;
				align-items: stretch;

				gap: 10px;

				overflow-x: auto;
				overflow-y: hidden;

				padding:
					2px
					2px
					8px;

				scrollbar-width: thin;
				scrollbar-color:
					#d6deea
					transparent;
			}

			.tsb-task-row {
				min-height: 112px;
			}

			.tsb-task-row::-webkit-scrollbar,
			.tsb-completed-row::-webkit-scrollbar {
				height: 6px;
			}

			.tsb-task-row::-webkit-scrollbar-thumb,
			.tsb-completed-row::-webkit-scrollbar-thumb {
				background: #d6deea;
				border-radius: 20px;
			}


			/* =================================================
			   TASK CARD
			================================================= */

			.tsb-task-card {
				position: relative;

				width: 255px;
				min-width: 255px;
				height: 108px;

				padding:
					13px
					14px
					12px
					15px;

				border: 1px solid;
				border-radius: 13px;

				cursor: grab;

				user-select: none;

				overflow: hidden;

				transition:
					transform 0.2s ease,
					box-shadow 0.2s ease,
					filter 0.2s ease;
			}

			.tsb-task-card:active {
				cursor: grabbing;
			}

			.tsb-task-card::before {
				content: "";

				position: absolute;

				left: -1px;
				top: 21px;

				width: 5px;
				height: 40px;

				border-radius:
					0
					6px
					6px
					0;

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
					rgba(
						255,
						255,
						255,
						0.28
					);

				pointer-events: none;
			}

			.tsb-task-card:hover {
				transform:
					translateY(-4px);

				box-shadow:
					0 12px 24px
					rgba(15, 23, 42, 0.10);

				filter:
					saturate(1.05);

				z-index: 3;
			}


			/* =================================================
			   DRAG
			================================================= */

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


			/* =================================================
			   CARD COLORS
			================================================= */

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


			/* =================================================
			   SEQUENCE
			================================================= */

			.tsb-sequence {
				position: absolute;

				left: 14px;
				top: 12px;

				width: 28px;
				height: 28px;

				display: flex;
				align-items: center;
				justify-content: center;

				border-radius: 8px;

				background:
					rgba(
						255,
						255,
						255,
						0.88
					);

				border:
					1px solid
					rgba(
						148,
						163,
						184,
						0.22
					);

				font-size: 12px;
				font-weight: 750;

				color: #111827;

				box-shadow:
					0 3px 8px
					rgba(15, 23, 42, 0.06);
			}


			/* =================================================
			   STATUS
			================================================= */

			.tsb-status {
				position: absolute;

				right: 12px;
				top: 12px;

				height: 25px;

				display: inline-flex;
				align-items: center;

				gap: 6px;

				padding: 0 10px;

				border-radius: 20px;

				font-size: 10px;
				font-weight: 700;

				white-space: nowrap;
			}

			.tsb-status-dot {
				width: 7px;
				height: 7px;

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


			/* =================================================
			   TASK TEXT
			================================================= */

			.tsb-task-title {
				position: relative;
				z-index: 2;

				margin-top: 42px;

				font-size: 13px;
				font-weight: 720;
				line-height: 1.25;

				color: #111827;

				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}

			.tsb-task-id {
				position: relative;
				z-index: 2;

				margin-top: 6px;

				font-size: 10px;
				font-weight: 500;

				color: #667b9c;

				white-space: nowrap;
				overflow: hidden;
				text-overflow: ellipsis;
			}


			/* =================================================
			   COMPLETED
			================================================= */

			.tsb-completed-wrapper {
				margin-top: 2px;

				border-top:
					1px solid #e7ecf2;
			}

			.tsb-completed-header {
				height: 42px;

				display: flex;
				align-items: center;
				justify-content: space-between;

				padding: 0 10px;

				border-radius: 10px;

				cursor: pointer;

				transition:
					background 0.15s ease;
			}

			.tsb-completed-header:hover {
				background: #f8fafc;
			}

			.tsb-completed-left {
				display: flex;
				align-items: center;

				gap: 9px;

				font-size: 12px;
				font-weight: 680;

				color: #1f2937;
			}

			.tsb-completed-arrow {
				width: 16px;

				font-size: 19px;

				text-align: center;

				color: #26364d;

				transition:
					transform 0.2s ease;
			}

			.tsb-completed-wrapper.open
			.tsb-completed-arrow {
				transform: rotate(90deg);
			}

			.tsb-completed-count {
				min-width: 28px;
				height: 28px;

				display: flex;
				align-items: center;
				justify-content: center;

				padding: 0 9px;

				border-radius: 20px;

				background: #d8f8e9;
				color: #078b52;

				font-size: 11px;
				font-weight: 750;
			}

			.tsb-completed-content {
				display: none;

				padding:
					4px
					2px
					8px;
			}

			.tsb-completed-wrapper.open
			.tsb-completed-content {
				display: block;
			}

			.tsb-completed-card {
				cursor: pointer;
			}


			/* =================================================
			   EMPTY
			================================================= */

			.tsb-no-task {
				min-height: 95px;

				display: flex;
				align-items: center;
				justify-content: center;

				width: 100%;

				border:
					1px dashed #dce4ee;

				border-radius: 12px;

				background: #fafcff;

				font-size: 11px;

				color: #94a3b8;
			}

			.tsb-empty {
				padding: 55px 20px;

				text-align: center;

				border:
					1px dashed #dce4ee;

				border-radius: 14px;

				background: #fafcff;

				font-size: 13px;

				color: #718096;
			}


			/* =================================================
			   LOADING
			================================================= */

			.tsb-loading {
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

				border:
					3px solid #e5e7eb;

				border-top-color:
					#5364f5;

				border-radius: 50%;

				animation:
					tsb-spin
					0.7s
					linear
					infinite;
			}

			@keyframes tsb-spin {
				to {
					transform:
						rotate(360deg);
				}
			}


			/* =================================================
			   RESPONSIVE
			================================================= */

			@media (max-width: 900px) {

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

			}

		</style>
	`).appendTo("head");


	// =========================================================
	// ESCAPE HTML
	// =========================================================

	function escape_html(value) {
		if (
			value === null ||
			value === undefined
		) {
			return "";
		}

		return $("<div>")
			.text(String(value))
			.html();
	}


	// =========================================================
	// INITIAL
	// =========================================================

	function get_initial(name) {
		const value =
			String(name || "").trim();

		if (!value) {
			return "?";
		}

		return value
			.charAt(0)
			.toUpperCase();
	}


	// =========================================================
	// NORMALIZE STATUS
	// =========================================================

	function normalize_status(status) {
		return String(status || "")
			.trim()
			.toLowerCase()
			.replace(/_/g, "-")
			.replace(/\s+/g, "-");
	}


	// =========================================================
	// STATUS CLASS
	// =========================================================

	function get_status_class(status) {
		const value =
			normalize_status(status);

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


	// =========================================================
	// CARD COLOR
	// =========================================================

	function get_card_color(status) {
		const value =
			normalize_status(status);

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


	// =========================================================
	// TASK CARD
	// =========================================================

	function get_task_card(
		task,
		index,
		completed = false
	) {
		const status =
			task.status ||
			(completed
				? "Completed"
				: "Open");

		const status_class =
			get_status_class(status);

		const card_color =
			get_card_color(status);

		const sequence =
			completed
				? index + 1
				: (
					task.custom_sequence ||
					index + 1
				);

		return `
			<div
				class="
					tsb-task-card
					${card_color}
					${completed
				? "tsb-completed-card"
				: ""
			}
				"
				data-task="${escape_html(task.name)}"
				${completed
				? ""
				: 'data-active-task="1"'
			}
			>

				<div class="tsb-sequence">
					${sequence}
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


				<div
					class="tsb-task-title"
					title="${escape_html(
				task.subject ||
				task.name
			)}"
				>
					${escape_html(
				task.subject ||
				task.name
			)}
				</div>


				<div class="tsb-task-id">
					${escape_html(task.name)}
				</div>

			</div>
		`;
	}


	// =========================================================
	// TECHNICIAN SECTION
	// =========================================================

	function render_technician(
		data,
		index
	) {
		const employee =
			data.employee || "";

		const employee_name =
			data.employee_name ||
			employee;

		const tasks =
			Array.isArray(data.tasks)
				? data.tasks
				: [];

		const completed_tasks =
			Array.isArray(
				data.completed_tasks
			)
				? data.completed_tasks
				: [];


		const active_html =
			tasks.length
				? tasks
					.map(
						(task, task_index) =>
							get_task_card(
								task,
								task_index,
								false
							)
					)
					.join("")
				: `
					<div class="tsb-no-task">
						No active tasks
					</div>
				`;


		const completed_html =
			completed_tasks.length
				? completed_tasks
					.map(
						(task, task_index) =>
							get_task_card(
								task,
								task_index,
								true
							)
					)
					.join("")
				: `
					<div class="tsb-no-task">
						No completed tasks
					</div>
				`;


		return `
			<div
				class="tsb-technician"
				data-employee="${escape_html(employee)}"
			>

				<div class="tsb-technician-header">

					<div
						class="
							tsb-avatar
							tsb-avatar-${index % 5}
						"
					>
						${escape_html(
			get_initial(
				employee_name
			)
		)}
					</div>


					<div class="tsb-tech-info">

						<div class="tsb-tech-name">
							${escape_html(
			employee_name
		)}
						</div>

						<div class="tsb-tech-id">
							${escape_html(
			employee
		)}
						</div>

					</div>

				</div>


				<div
					class="tsb-task-row"
					data-employee="${escape_html(employee)}"
				>
					${active_html}
				</div>


				<div class="tsb-completed-wrapper">

					<div class="tsb-completed-header">

						<div class="tsb-completed-left">

							<span class="tsb-completed-arrow">
								›
							</span>

							<span>
								Completed Tasks
							</span>

						</div>


						<div class="tsb-completed-count">
							${completed_tasks.length}
						</div>

					</div>


					<div class="tsb-completed-content">

						<div class="tsb-completed-row">
							${completed_html}
						</div>

					</div>

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

		if (
			!Array.isArray(data) ||
			!data.length
		) {
			$board.html(`
				<div class="tsb-empty">
					No tasks found for the selected technician.
				</div>
			`);

			return;
		}

		const html =
			data
				.map(
					(row, index) =>
						render_technician(
							row,
							index
						)
				)
				.join("");

		$board.html(html);

		setup_completed_toggle();

		setup_task_click();

		setup_drag_drop();
	}


	// =========================================================
	// COMPLETED TOGGLE
	// =========================================================

	function setup_completed_toggle() {
		$main
			.find(".tsb-completed-header")
			.off(".tsb")
			.on(
				"click.tsb",
				function () {
					$(this)
						.closest(
							".tsb-completed-wrapper"
						)
						.toggleClass("open");
				}
			);
	}


	// =========================================================
	// TASK CLICK
	// =========================================================

	function setup_task_click() {
		$main
			.find(".tsb-task-card")
			.off("dblclick.tsb")
			.on(
				"dblclick.tsb",
				function () {
					const task =
						$(this).attr(
							"data-task"
						);

					if (!task) {
						return;
					}

					frappe.set_route(
						"Form",
						"Task",
						task
					);
				}
			);
	}


	// =========================================================
	// UPDATE VISUAL SEQUENCE
	// =========================================================

	function update_sequence_labels($row) {
		$row
			.children(
				".tsb-task-card"
			)
			.each(
				function (index) {
					$(this)
						.find(
							".tsb-sequence"
						)
						.text(
							index + 1
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
			.children(
				".tsb-task-card"
			)
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
		task_names
	) {
		if (
			!employee ||
			!Array.isArray(task_names) ||
			!task_names.length
		) {
			return;
		}

		if (is_saving) {
			return;
		}

		is_saving = true;

		frappe.call({
			method:
				"fleet.fleet.page.task_sequence_board.task_sequence_board.update_task_sequence",

			args: {
				employee: employee,

				tasks:
					JSON.stringify(
						task_names
					),
			},

			freeze: false,

			callback(r) {
				is_saving = false;

				if (
					r.message &&
					r.message.status ===
					"success"
				) {
					frappe.show_alert({
						message:
							__(
								"Task sequence updated"
							),

						indicator:
							"green",
					});
				}
			},

			error() {
				is_saving = false;

				frappe.show_alert({
					message:
						__(
							"Unable to update task sequence"
						),

					indicator:
						"red",
				});

				refresh_board();
			},
		});
	}


	// =========================================================
	// DRAG & DROP
	// =========================================================

	function setup_drag_drop() {
		$main
			.find(".tsb-task-row")
			.each(function () {
				const element = this;

				const $row =
					$(element);


				// Don't initialize sortable
				// if there are no actual task cards.
				if (
					!$row
						.children(
							".tsb-task-card"
						)
						.length
				) {
					return;
				}


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
							animation: 180,

							draggable:
								".tsb-task-card",

							ghostClass:
								"tsb-dragging-card",

							chosenClass:
								"tsb-chosen-card",

							dragClass:
								"tsb-moving-card",

							forceFallback:
								false,

							fallbackTolerance:
								3,

							onEnd(evt) {
								if (
									evt.oldIndex ===
									evt.newIndex
								) {
									return;
								}

								update_sequence_labels(
									$row
								);

								const employee =
									$row.attr(
										"data-employee"
									);

								const task_names =
									get_task_order(
										$row
									);

								save_sequence(
									employee,
									task_names
								);
							},
						}
					);
			});
	}


	// =========================================================
	// MULTISELECT TECHNICIAN FILTER
	// =========================================================

	function setup_technician_filter() {
		const $filter =
			$main.find(
				"#tsb-technician-filter"
			);

		$filter.empty();


		technician_control =
			frappe.ui.form.make_control({
				parent: $filter,

				df: {
					fieldtype:
						"MultiSelectList",

					fieldname:
						"technicians",

					label:
						__("Technician"),

					placeholder:
						__(
							"Select Technician"
						),


					// =========================================
					// ONLY TECHNICIANS
					// =========================================

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


					// =========================================
					// APPLY FILTER IMMEDIATELY
					// =========================================

					change() {
						let technicians =
							technician_control
								.get_value() ||
							[];

						if (
							!Array.isArray(
								technicians
							)
						) {
							technicians =
								technicians
									? [
										technicians
									]
									: [];
						}

						load_board(
							technicians
						);
					},
				},

				render_input:
					true,
			});


		technician_control.refresh();
	}


	// =========================================================
	// GET SELECTED TECHNICIANS
	// =========================================================

	function get_selected_technicians() {
		if (!technician_control) {
			return [];
		}

		let technicians =
			technician_control
				.get_value() || [];

		if (
			!Array.isArray(
				technicians
			)
		) {
			technicians =
				technicians
					? [technicians]
					: [];
		}

		return technicians;
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


		if (
			!Array.isArray(
				technicians
			)
		) {
			technicians =
				technicians
					? [technicians]
					: [];
		}


		$board.html(`
			<div class="tsb-loading">

				<div class="tsb-spinner">
				</div>

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
				render_board(
					r.message || []
				);
			},

			error() {
				$board.html(`
					<div class="tsb-empty">
						Unable to load Task Sequence Board.
					</div>
				`);
			},
		});
	}


	// =========================================================
	// REFRESH BOARD
	// =========================================================

	function refresh_board() {
		const technicians =
			get_selected_technicians();

		load_board(
			technicians
		);
	}


	// =========================================================
	// NEW TASK
	// =========================================================

	$main
		.find(
			".tsb-new-task-btn"
		)
		.on(
			"click",
			function () {
				frappe.new_doc(
					"Task"
				);
			}
		);


	// =========================================================
	// REFRESH
	// =========================================================

	$main
		.find(
			".tsb-refresh-btn"
		)
		.on(
			"click",
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