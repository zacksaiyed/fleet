# Fleet APIs (code)

All mobile/admin HTTP APIs live under `fleet/apis/`. Same behaviour as Postman collections in `docs/fleet_api_samples/postman_by_method/`.

**Base URL (local):** `http://127.0.0.1:8004`  
**Auth:** session cookie after login, or `Authorization: token api_key:api_secret`

## Folder map

| Folder / module | Postman folder | Description |
|-----------------|----------------|-------------|
| `auth.py` | Login | Mobile login/logout/session; desk uses `/api/method/login` |
| `password.py` | Change Password | Self + admin change password |
| `dashboard.py` | Dashboard | Tile counts (`counts` / `fleet_dashboard_counts_v2`) |
| `job.py` | Job (admin one-shot) | list, create, save, action, detail v2 |
| `job_one_shot.py` | Job (4 sections) | vehicle context, load, patch save (job/items/images) |
| `task.py` | Task + Job (technician) | Wraps `fleet.v2.task_v2` |
| `customer.py` | Customer | Helpers + use REST `/api/resource/Customer` |
| `vehicle.py` | Vehicle | Picker, exists, details, types |
| `material_transfer.py` | Material Transfer | Wraps `fleet.v2.inventory_v2` |
| `registry.py` | — | JSON catalog for tooling |

## Quick examples

```http
POST /api/method/login
Content-Type: application/json
{"usr":"Administrator","pwd":"Admin@123"}
```

```http
POST /api/method/fleet.apis.dashboard.counts
Cookie: sid=...
Content-Type: application/json
{}
```

```http
POST /api/method/fleet.apis.job.save_v2
Cookie: sid=...
Content-Type: application/json
{"name":"JOB-2026-08-000158","item_installed_removed":[...]}
```

**Technician — plate lookup (4 sections):**

```http
GET /api/method/fleet.apis.job_one_shot.vehicle_context?vehicle_number=GJ05SY0888&task=TASK-0001&task_type=Checkup
Cookie: sid=...
```

**Technician — one-shot save:**

```http
POST /api/method/fleet.apis.job_one_shot.save
Cookie: sid=...
Content-Type: application/json

{
  "name": "JOB-2026-08-000158",
  "job": {
    "make": "Hitachi",
    "model": "EX07",
    "color": "White",
    "type": "Car",
    "done_comment": "All sections saved in one shot"
  },
  "items": {
    "create": [
      {
        "item_type": "GPS Device",
        "item": "868373073604185",
        "item_name": "G Teltonika 073604185",
        "brand": "Teltonika",
        "installed_or_removed": "Installed"
      }
    ],
    "update": [{ "id": "abc123xyz", "installed_or_removed": "Removed" }],
    "delete": ["row-name-to-drop"]
  },
  "images": {
    "create": [{ "image": "/files/new-uploaded.jpg", "comment": "New photo" }],
    "delete": ["image-row-name"]
  }
}
```

Flat plate API (unchanged): `fleet.apis.task.get_vehicle_details` or `fleet.v2.task_v2.get_vehicle_details`.

## UAT Server Script names

On UAT, some URLs are short (`/api/method/fleet_job_list_v2`) via **Server Scripts**.  
On bench code use **`fleet.apis.job.fleet_job_list_v2`** (or `list_v2`) — no Server Script required.

## Legacy implementations

- `fleet/mobile_api/` — original mobile auth & external
- `fleet/v2/task_v2.py`, `inventory_v2.py` — technician task/job/transfer logic

`fleet/apis/*` is the **single entry folder** for new integrations; it delegates to v2 where logic already exists.
