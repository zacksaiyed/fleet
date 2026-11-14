API_CATALOG = {
	"login": {
		"module": "auth",
		"endpoints": [
			{"method": "POST", "path": "/api/method/login", "note": "Frappe built-in (usr, pwd)"},
			{"method": "POST", "path": "/api/method/fleet.apis.auth.login", "note": "Mobile Technician"},
			{"method": "POST", "path": "/api/method/fleet.apis.auth.logout"},
			{"method": "GET", "path": "/api/method/fleet.apis.auth.get_session_info"},
		],
	},
	"change_password": {
		"module": "password",
		"endpoints": [
			{"method": "POST", "path": "/api/method/fleet.apis.password.change_password"},
			{"method": "POST", "path": "/api/method/fleet.apis.password.admin_change_password"},
		],
	},
	"dashboard": {
		"module": "dashboard",
		"endpoints": [
			{"method": "POST", "path": "/api/method/fleet.apis.dashboard.counts"},
			{"method": "POST", "path": "/api/method/fleet.apis.dashboard.fleet_dashboard_counts_v2"},
		],
	},
	"job_admin": {
		"module": "job",
		"endpoints": [
			{"method": "POST", "path": "/api/method/fleet.apis.job.list_v2"},
			{"method": "POST", "path": "/api/method/fleet.apis.job.create_v2"},
			{"method": "POST", "path": "/api/method/fleet.apis.job.save_v2"},
			{"method": "POST", "path": "/api/method/fleet.apis.job.action_v2"},
			{"method": "POST", "path": "/api/method/fleet.apis.job.detail_v2"},
			{"method": "PUT", "path": "/api/resource/Job/{name}", "note": "REST one-shot save alternative"},
		],
	},
	"job_one_shot": {
		"module": "job_one_shot",
		"endpoints": [
			{
				"method": "GET",
				"path": "/api/method/fleet.apis.job_one_shot.vehicle_context",
				"note": "vehicle_number, task, task_type — vehicle + vehicle_items + empty job/items/images",
			},
			{"method": "POST", "path": "/api/method/fleet.apis.job_one_shot.load", "note": "name — full 4 sections from Job"},
			{"method": "POST", "path": "/api/method/fleet.apis.job_one_shot.save", "note": "name + job + items + images sections"},
			{"method": "GET", "path": "/api/method/fleet.apis.task.get_vehicle_details", "note": "legacy flat response"},
		],
	},
	"task_technician": {
		"module": "task",
		"endpoints": [
			{"method": "POST", "path": "/api/method/fleet.apis.task.get_my_tasks"},
			{"method": "POST", "path": "/api/method/fleet.apis.task.get_job"},
			{"method": "POST", "path": "/api/method/fleet.apis.task.update_job"},
			{"method": "POST", "path": "/api/method/fleet.apis.task.job_action"},
		],
	},
	"customer": {
		"module": "customer",
		"endpoints": [
			{"method": "GET", "path": "/api/resource/Customer", "note": "Standard REST list/detail"},
			{"method": "POST", "path": "/api/resource/Customer", "note": "Create"},
			{"method": "PUT", "path": "/api/resource/Customer/{name}", "note": "Update"},
			{"method": "POST", "path": "/api/method/fleet.apis.customer.list_with_vehicle_counts"},
		],
	},
	"vehicle": {
		"module": "vehicle",
		"endpoints": [
			{"method": "GET", "path": "/api/resource/Vehicle", "note": "Standard REST"},
			{"method": "POST", "path": "/api/method/fleet.apis.vehicle.picker"},
			{"method": "POST", "path": "/api/method/fleet.apis.vehicle.exists"},
			{"method": "POST", "path": "/api/method/fleet.apis.vehicle.details"},
		],
	},
	"material_transfer": {
		"module": "material_transfer",
		"endpoints": [
			{"method": "POST", "path": "/api/method/fleet.apis.material_transfer.get_my_transfers"},
			{"method": "POST", "path": "/api/method/fleet.apis.material_transfer.create_transfer"},
			{"method": "POST", "path": "/api/method/fleet.apis.material_transfer.respond_transfer"},
		],
	},
}


def get_catalog():
	return API_CATALOG
