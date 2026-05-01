app_name = "fleet"
app_title = "Fleet"
app_publisher = "XBarq Technologies"
app_description = "Fleet Management"
app_email = "info@xbarq.in"
app_license = "mit"
app_home = "/fleet-track"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "fleet",
# 		"logo": "/assets/fleet/logo.png",
# 		"title": "Fleet",
# 		"route": "/fleet",
# 		"has_permission": "fleet.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/fleet/css/fleet.css"
# app_include_js = "/assets/fleet/js/fleet.js"

# include js, css files in header of web template
# web_include_css = "/assets/fleet/css/fleet.css"
# web_include_js = "/assets/fleet/js/fleet.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "fleet/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views

doctype_js = {
  "Task"     : "public/js/task.js",
  "User"     : "public/js/user.js",
  "Item"     : "public/js/item.js",
  "Address"  : "public/js/address.js",
  "Employee" : "public/js/employee.js",
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
doctype_list_js = {
  "Item":     "public/js/item_list.js",
  "Customer": "public/js/customer_list.js",
  "Vehicle":  "public/js/vehicle_list.js",
  "Employee": "public/js/employee_list.js",
  "Task":     "public/js/task_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "fleet/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
home_page = "app/fleet-track"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "fleet.utils.jinja_methods",
# 	"filters": "fleet.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "fleet.install.before_install"
# after_install = "fleet.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "fleet.uninstall.before_uninstall"
# after_uninstall = "fleet.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "fleet.utils.before_app_install"
# after_app_install = "fleet.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "fleet.utils.before_app_uninstall"
# after_app_uninstall = "fleet.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "fleet.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

on_socket_event = {
    "join_job_room":  "fleet.override.job_chat.on_join_job_room",
    "leave_job_room": "fleet.override.job_chat.on_leave_job_room",
}

permission_query_conditions = {
	"Task":               "fleet.custom_py.permissions.task_permission_query",
	"Job":                "fleet.custom_py.permissions.job_permission_query",
	"Material Transfer":  "fleet.fleet.doctype.material_transfer.material_transfer.mt_permission_query",
}

has_permission = {
	"Task":               "fleet.custom_py.permissions.task_has_permission",
	"Job":                "fleet.custom_py.permissions.job_has_permission",
	"Material Transfer":  "fleet.fleet.doctype.material_transfer.material_transfer.mt_has_permission",
}
# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "User": {
        "validate": "fleet.erpnext_events.user_warehouse_hooks.validate_user_roles",
        "on_update": "fleet.erpnext_events.user_warehouse_hooks.on_update_user_roles"
    },
    "Job": {
        "after_insert": "fleet.custom_py.task_assignment.handle_job_assignment",
        "on_update": [
            "fleet.custom_py.task_hooks.sync_job_status_to_row",
            "fleet.custom_py.task_assignment.handle_job_assignment",
        ],
    },
    "Task": {
        "validate": "fleet.fleet.doctype.task.task.validate",
        "after_insert": "fleet.custom_py.task_assignment.handle_assignment",
        "on_update": [
            "fleet.override.task.sync_vehicle_data",               # Vehicle sync on Complete
            "fleet.custom_py.task_hooks.on_task_update",           # Create Jobs for new rows
            "fleet.custom_py.task_assignment.handle_assignment",   # Re-assign on update
        ],
    },
    "Employee": {
        # "after_insert": "fleet.erpnext_events.employee.sync_user_with_employee",
        "validate": "fleet.erpnext_events.employee.validate_employee",
        "on_update": "fleet.erpnext_events.employee.sync_user_with_employee"
    },
    "Vehicle": {
        "validate": "fleet.erpnext_events.vehicle.validate_vehicle"
    },
    "Customer": {
        "after_insert": [
            "fleet.override.customer_warehouse.set_customer_warehouse"
        ],
        "on_update": [
            "fleet.override.customer_warehouse.set_customer_warehouse"
        ],
        "on_trash": [
            "fleet.override.customer_warehouse.set_customer_warehouse"
        ]    
    },
    "Item": {
        "before_insert": "fleet.override.item.generate_item_details"
    }
# 		"on_trash": "method",
#       "on_submit": "method"
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"fleet.tasks.all"
# 	],
# 	"daily": [
# 		"fleet.tasks.daily"
# 	],
# 	"hourly": [
# 		"fleet.tasks.hourly"
# 	],
# 	"weekly": [
# 		"fleet.tasks.weekly"
# 	],
# 	"monthly": [
# 		"fleet.tasks.monthly"
# 	],
# }

scheduler_events = {
    "cron": {
        # Run every 5 minutes — auto-reject tasks not accepted within 1 hour
        "*/5 * * * *": [
            "fleet.scheduled.task_auto_reject.auto_reject_unaccepted_tasks"
        ],
    },
}

# Testing
# -------

# before_tests = "fleet.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "fleet.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "fleet.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["fleet.utils.before_request"]
# after_request = ["fleet.utils.after_request"]

# Job Events
# ----------
# before_job = ["fleet.utils.before_job"]
# after_job = ["fleet.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------
on_session_creation = "fleet.mobile_api.auth.enforce_simultaneous_sessions"

# auth_hooks = [
# 	"fleet.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {"dt": "Workflow State", "filters": [
        ["name", "in", [
            "Completed", "Open", "Cancelled", "In Review", "On Hold",
            "In Progress", "Accepted", "Initiated", "Approval Pending",
            "Approved", "Rejected"
        ]]
    ]},
    {"dt": "Custom DocPerm", "filters": [
        ["role", "in", ["Fleet Administrator", "Fleet Manager"]]
    ]},
    {"dt": "Workflow","filters": [
        [
            "name", "in", [
                "Material Transfer Workflow"
            ]
        ]
    ]},
    
    {"dt": "Translation","filters": [
        [
            "name", "in", [
                "rgopehkm8k"
            ]
        ]
    ]},
]