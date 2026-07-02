# Fleet Management Application — Comprehensive Documentation

> **App:** Fleet (`fleet`)  
> **Publisher:** XBarq Technologies  
> **Framework:** Frappe v15 
> **Hosting:** Frappe Cloud  

---

## Table of Contents

1. [Site Initialization / Reset](#1-site-initialization--reset)
2. [Application Flow](#2-application-flow)
3. [API Documentation (Mobile APIs)](#3-api-documentation-mobile-apis)
4. [Production SOPs & Troubleshooting](#4-production-sops--troubleshooting)
5. [Customizations](#5-customizations)
6. [Contact / Escalation Matrix](#6-contact--escalation-matrix)
7. [Scheduled / Background Jobs](#7-scheduled--background-jobs)
8. [Installed Apps & Dependencies](#8-installed-apps--dependencies)
9. [External Integrations — Firebase FCM](#9-external-integrations--firebase-fcm)
10. [Known Issues, Limitations & Workarounds](#10-known-issues-limitations--workarounds)
11. [Deployment & Migration Process](#11-deployment--migration-process)

---

## 1. Site Initialization / Reset

### 1.1 What Gets Auto-Applied on Install / Migrate

When the Fleet app is installed (`bench install-app fleet`) or migrated (`bench migrate`), Frappe automatically syncs all **fixtures** defined in `hooks.py`. No manual install script exists.

#### Fixtures Synced Automatically

| Fixture | Contents |
|---|---|
| **Workflow State** | 11 states: Completed, Open, Cancelled, In Review, On Hold, In Progress, Accepted, Initiated, Approval Pending, Approved, Rejected |
| **Custom DocPerm** | Role-level permissions for Fleet Administrator and Fleet Manager across all doctypes |
| **Workflow** | Material Transfer Workflow (Initiated → Approval Pending → Approved/Rejected/Cancelled) |
| **Translation** | English: "Task Type" displays as "Job Type" in the UI |
| **Report** | Vehicle Item Warehouse Status (Script Report) |

Additional fixtures bundled in `fleet/fleet/fixtures/`:

| Fixture | Contents |
|---|---|
| `role.json` | 5 roles: Technician, Material Transfer User, Fleet Administrator, Fleet Manager, Support Team |
| `designation.json` | Technician, Support, Administrator, Manager |
| `task_type.json` | Installation, Checkup, Removal, Accessory |
| `warehouse_type.json` | Customer, Technician |
| `workflow_action_master.json` | Accept, Done, Complete, Re Open, Start, Hold, Cancel |
| `brand.json` | Pre-configured brands (Airtel/MTN → SIM; Wazambi/GTMS → GPS Device; Tramigo → Temperature; etc.) |
| `item_type.json` | GPS Device, SIM, Temperature, Fuel Sensor (with icons) |
| `module_profile.json` | "Fleet" module profile — blocks all non-Fleet ERPNext modules for technician users |
| `translation.json` | UI label "Task Type" → "Job Type" |
| `workflow.json` | Material Transfer Workflow definition |
| `custom_html_block.json` | Support Dashboard HTML block (technician cards grid) |

### 1.2 Required Apps (Install Order)

```
bench get-app frappe
bench get-app erpnext
bench get-app fleet
```

ERPNext **must** be installed before Fleet. Fleet depends on ERPNext doctypes (Item, Warehouse, Customer, Employee, Task, Stock Entry, etc.).

### 1.3 Manual Steps After Site Creation / Reset

1. **Company setup** — Create Company record; set abbreviation (used in warehouse naming: `{Customer} - {abbr}`).

2. **Firebase configuration** — Go to **Firebase Settings** (single doctype) → paste the full Firebase service account JSON from Google Cloud. Without this, FCM push notifications will silently fail.

3. **Store Warehouse** — Create a Warehouse named `Stores - {abbr}` (or any warehouse named "Stores"). This is the default warehouse for newly imported items (`override/item.py` → `_get_store_warehouse()`).

4. **Default Item Group** — Ensure at least one non-group Item Group exists. Used as fallback when creating items via the Vehicle Data Import flow.

5. **Brands** — Brands fixture loads pre-configured brands. Add additional brands via Item master if needed and link `custom_item_type`.

6. **Employee → User sync** — Create Employee records. On save, the system auto-creates linked User accounts with the correct role and warehouse. The `designation` field must match one of: Technician, Support, Administrator, Manager (controls which roles the User gets).

7. **Customer → Warehouse auto-creation** — When a Customer record is created/saved, a Warehouse (`{Customer Name} - {abbr}`, type: Customer) is automatically created via `override/customer_warehouse.py`. No manual step needed.

8. **Scheduler** — Ensure bench workers are running: `bench start` (dev) or systemd services in production. The auto-reject cron runs every 5 minutes.

### 1.4 Role Summary

| Role | Access Level |
|---|---|
| **System Manager** | Full system access |
| **Fleet Administrator** | Full Fleet access, can complete tasks/jobs, manage all records |
| **Fleet Manager** | Same as Fleet Administrator (minor differences in some reports) |
| **Support Team** | Creates/manages tasks, assigns technicians, approves jobs, chats |
| **Technician** | Mobile app only; sees own tasks/jobs; restricted to own warehouse |
| **Material Transfer User** | Can initiate/submit material transfers |

---

## 2. Application Flow

### 2.1 Overview

```
Customer → Task (with address) → Jobs (per vehicle/service) → Technician (mobile)
       ↓                              ↓
  Warehouse auto-created          Stock Entry (items moved)
                                      ↓
                                  Vehicle updated (items installed/removed)
```

### 2.2 Task Lifecycle

```
Open → Accepted → In Progress → In Review → Completed
                                          ↘ On Hold
     ↘ Rejected
```

**Open (created by Support)**
- Fields set: `custom_customer`, `custom_address`, `custom_complete_address`, `custom_date`, subject (auto-built as `{customer} — {address_title}`)
- Support assigns technician via `custom_assign_to` (Link→Employee)
- `custom_assigned_at` stamped automatically on assignment

**DB changes on Task creation:**
- `tabTask` row inserted
- `tabTask Job` child rows created (one per job type/vehicle combination)
- ToDo and DocShare created for assigned technician

**Accepted / Rejected (by Technician via mobile)**
- Technician can accept or reject with comment
- Rejection: status=Rejected, `custom_reject_comment` stored; Support can reassign
- On reassign: status returns to Open; all linked non-final Jobs updated to new technician

**In Progress (by Technician)**
- At least one Job moves to In Progress

**In Review**
- Technician marks Job as "Done" (In Progress → In Review)
- Task auto-transitions to In Review when all Jobs are In Review or Completed

**Completed (by Support)**
- Support reviews and marks Task Completed
- `sync_vehicle_data()` fires (`override/task.py`): Vehicle records updated based on all Jobs
- `custom_completed_by` and `custom_completed_on` stamped on Task

**On Hold**
- Technician or Support can hold a Job; Task reflects On Hold status

### 2.3 Job Lifecycle

```
Pending → In Progress → In Review → Completed
                     ↘ On Hold → In Progress
```

**Job creation** — jobs are created from:
- Task Job rows (via Support's "Add Jobs" dialog on the Task form)
- Mobile: `create_job_for_task` API (technician creates job during field work)

**Fields auto-populated on Job save (`job.py → before_save`):**
- `assigned_technician` — from Task's `custom_assign_to`
- `technician_warehouse` — from technician's linked Warehouse
- `customer_warehouse` — from Vehicle's customer's Warehouse
- `vehicle_number`, `customer`, `make`, `model`, `color`, `type` — from Task/Vehicle
- Date — from `task.custom_date`
- Status auto-advances Pending→In Progress if item rows exist

**Job Done (Technician → In Review):**
- Requires: `done_comment` + at least 1 job image
- `unread_count_support` incremented (triggers chat badge for Support)
- FCM push to Support

**Job Completed (Support → Completed):**
- `_handle_warehouse_movement()` fires:
  - Installed items: creates Stock Entry (Material Transfer) from technician warehouse → customer warehouse
  - Removed items: creates Stock Entry from customer warehouse → technician warehouse
  - Stock Entry has `custom_job` field set to the Job name (for deduplication)
- `_update_vehicle_items()` fires:
  - Installation job: creates/updates Vehicle record; appends `custom_vehicle_item` rows (status: Installed); attaches job images to Vehicle
  - Removal job: sets matching `custom_vehicle_item` rows to status: Removed
  - Checkup/Accessory: validates item is installed on vehicle (no status change)
- `custom_current_warehouse` on Item updated via `update_item_warehouse()`

**DB changes on Job Completed:**
```
tabJob → status = Completed, completed_by_support, completed_on_support
tabStock Entry → created (type: Material Transfer)
tabStock Entry Detail → one row per item
tabBin → qty adjusted
tabVehicle Item → status updated (Installed/Removed)
tabItem → custom_current_warehouse updated
```

### 2.4 Material Transfer Lifecycle

Used to move items between technician warehouses or back to the Store.

```
Initiated → Approval Pending → Approved (stock entry created)
                             ↘ Rejected
          ↘ Cancelled
```

**Create:** Technician selects target warehouse + items.  
**Submit (Transfer Material action):** State → Approval Pending; FCM push + Notification Log sent to target warehouse users.  
**Approve:** Target technician/Support approves → state=Approved, docstatus=1 → Stock Entry created → `custom_current_warehouse` updated on all items.  
**Reject:** Reject reason saved; creator notified via FCM.  
**Cancel:** Cancels linked Stock Entry; items revert to source warehouse.

### 2.5 Item Import Flow (Data Import)

1. Support creates a Data Import record for **Item** doctype.
2. Fills in `custom_item_type`, `custom_brand`, `custom_sim_type`, `custom_country_code` on the Data Import form (shared fields for all rows in the batch).
3. Uploads CSV with item-specific columns (IMEI/serial/barcode etc.).
4. On import start, `CustomDataImport.start_import()` stores the shared fields in Redis cache.
5. `override/item.py → generate_item_details()` fires on `before_insert` for each Item:
   - Reads shared fields from Redis
   - Builds `item_code`, `item_name` from prefix + brand + last 9 chars of identifier
   - Sets `custom_current_warehouse` to Store warehouse
   - Generates barcode

### 2.6 Vehicle Import Flow (Data Import)

1. Support creates Data Import for **Vehicle** doctype.
2. CSV includes license plate, make, model, customer, and child table rows (`custom_vehicle_item`) with item codes and status.
3. `validate_vehicle()` runs on each Vehicle row:
   - Normalizes license plate (strip spaces, uppercase) → becomes the Vehicle's `name`
   - Re-syncs child row `parent` fields to the normalized name (fixes orphaned rows for plates with spaces)
   - Deduplicates `custom_vehicle_item` rows with the same `(item, status)` pair
   - Throws error if any "Installed" item does not exist in the Item master
   - Throws error if any "Installed" item is already marked Installed on another Vehicle
4. `after_insert_vehicle()` runs after Vehicle is saved:
   - Looks up customer's Warehouse (via `custom_customer_name`)
   - For each "Installed" `custom_vehicle_item` row: calls `update_item_warehouse()` to set `custom_current_warehouse` on the Item

### 2.7 Chat Flow (Support ↔ Technician)

- Support monitors the **Support Dashboard** page (auto-refreshes every 60 s).
- Real-time via WebSocket (`job_message` room per job).
- Message sent → `Job Message` record created → `unread_count_tech` or `unread_count_support` incremented → FCM push sent to the other party.
- On read → `mark_messages_read()` called → counter reset → `support_dashboard_read` event published.

---

## 3. API Documentation (Mobile APIs)

All mobile APIs are Frappe whitelisted methods. 

**Base URL:** `https://{site}/api/method/fleet.mobile_api.{module}.{function}`  
**Method:** `POST` (all, even read operations — Frappe convention)  
**Content-Type:** `application/json`  
**Authentication:** Cookie-based (`sid` from login response). Pass as cookie header.  
**Response format:** `{"message": <result>}` on success, `{"exc_type": "...", "exc": "..."}` on error.

---

### 3.1 Auth APIs (`fleet.mobile_api.auth`)

#### `login`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.login`  
**Auth:** None (guest-allowed)

**Request:**
```json
{
  "usr": "technician@example.com",
  "pwd": "password123",
  "token": "fcm_token_string",
  "device_id": "device_uuid"
}
```

**Response (success):**
```json
{
  "message": {
    "status": "success",
    "sid": "session_id_string",
    "user": {
      "name": "technician@example.com",
      "full_name": "John Doe",
      "employee": "EMP-0001",
      "warehouse": "John Doe - FT",
      "roles": ["Technician"]
    }
  }
}
```

**Error responses:**
- `403` — Wrong credentials
- `403` — User does not have Technician role
- `403` — Account disabled

**Notes:** Registers FCM token on login. Only Technician-role users can log in via mobile.

---

#### `logout`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.logout`  
**Auth:** Required (sid cookie)

**Request:** (no body)

**Response:** `{"message": "ok"}`

**Notes:** Deletes stored FCM token for this user.

---

#### `register_fcm_token`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.register_fcm_token`  
**Auth:** Required

**Request:**
```json
{ "token": "fcm_token", "device_id": "device_uuid" }
```

**Response:** `{"message": "ok"}`

---

#### `get_logged_in_user`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.get_logged_in_user`  
**Auth:** Required

**Response:**
```json
{
  "message": {
    "name": "user@example.com",
    "full_name": "John Doe",
    "employee": "EMP-0001",
    "warehouse": "John Doe - FT"
  }
}
```

---

#### `change_password`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.change_password`  
**Auth:** Required

**Request:**
```json
{ "old_password": "current", "new_password": "newpass" }
```

**Response:** `{"message": "ok"}`

**Error:** `{"message": "incorrect_password"}` if old password is wrong.

---

#### `get_profile`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.get_profile`  
**Auth:** Required

**Response:**
```json
{
  "message": {
    "employee": { "name": "EMP-0001", "employee_name": "John Doe", "designation": "Technician", ... },
    "user": { "email": "...", "full_name": "..." },
    "warehouse": "John Doe - FT"
  }
}
```

---

#### `get_session_info`

**Endpoint:** `POST /api/method/fleet.mobile_api.auth.get_session_info`  
**Auth:** Required

**Response:** Returns stored session user info from Redis. Used on mobile app launch to validate the stored session is still valid.

---

### 3.2 Inventory APIs (`fleet.mobile_api.inventory`)

#### `get_my_warehouse_inventory`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.get_my_warehouse_inventory`  
**Auth:** Required (Technician)

**Response:**
```json
{
  "message": {
    "GPS Device": [
      {
        "item": "ITEM-001",
        "item_name": "G Wazambi 123456789",
        "item_type": "GPS Device",
        "brand": "Wazambi",
        "qty": 1,
        "is_available": true,
        "blocked_by": null
      }
    ],
    "SIM": [ ... ]
  }
}
```

**Notes:** Excludes items in pending Material Transfers or active (non-Completed/Cancelled) Jobs.

---

#### `get_transfer_targets`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.get_transfer_targets`  
**Auth:** Required

**Response:**
```json
{
  "message": [
    { "warehouse": "Jane Smith - FT", "label": "Jane Smith", "type": "technician" },
    { "warehouse": "Stores - FT", "label": "Store", "type": "store" }
  ]
}
```

---

#### `get_my_transfers`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.get_my_transfers`  
**Auth:** Required

**Request:**
```json
{ "workflow_state": "Approval Pending" }
```
(Pass `null` or omit for all states)

**Response:** List of Material Transfer records (outgoing all states + incoming Approval Pending/Approved).

---

#### `get_transfer`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.get_transfer`

**Request:** `{ "name": "MT-2024-06-000001" }`

**Response:**
```json
{
  "message": {
    "name": "MT-2024-06-000001",
    "source": "John Doe - FT",
    "target": "Jane Smith - FT",
    "workflow_state": "Approval Pending",
    "can_approve": true,
    "can_cancel": false,
    "items": {
      "GPS Device": [ { "item": "...", "item_name": "..." } ]
    }
  }
}
```

---

#### `create_transfer`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.create_transfer`

**Request:**
```json
{
  "target": "Jane Smith - FT",
  "items": ["ITEM-001", "ITEM-002"]
}
```

**Response:** `{"message": "MT-2024-06-000001"}`

**Errors:**
- Item not in technician's warehouse
- Duplicate pending transfer already exists for same source+target

---

#### `submit_transfer`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.submit_transfer`

**Request:** `{ "name": "MT-2024-06-000001" }`

**Notes:** Applies "Transfer Material" workflow action (Initiated → Approval Pending). Sends FCM push to target warehouse users.

---

#### `cancel_transfer`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.cancel_transfer`

**Request:** `{ "name": "MT-2024-06-000001" }`

---

#### `respond_transfer`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.respond_transfer`

**Request:**
```json
{
  "name": "MT-2024-06-000001",
  "action": "Approve",
  "reject_reason": null
}
```
(`action`: `"Approve"` or `"Reject"`)

**Notes:** On Approve → Stock Entry created, item warehouses updated. On Reject → FCM push to creator.

---

#### `get_warehouse_items`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.get_warehouse_items`

**Request:** `{ "search": "123456" }`

**Response:** Items in technician's warehouse with `actual_qty > 0`, filtered by search term.

---

#### `check_vehicle`

**Endpoint:** `POST /api/method/fleet.mobile_api.inventory.check_vehicle`

**Request:** `{ "vehicle_number": "ABC1234", "customer": "General Motors" }`

**Response:**
```json
{
  "message": {
    "exists": true,
    "customer_match": true,
    "installed_items": [ { "item": "...", "item_type": "GPS Device" } ],
    "removed_items": [ ... ]
  }
}
```

---

### 3.3 Task / Job APIs (`fleet.mobile_api.tasks`)

#### `get_my_tasks`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_my_tasks`  
**Auth:** Required (Technician)

**Response:**
```json
{
  "message": {
    "today": [ { "name": "TASK-0001", "subject": "General Motors — Plot 5 Cairo Road", "status": "Accepted", "date": "2024-06-10", "lat": -15.41, "lng": 28.28, "job_count": 2, "unread_count": 1 } ],
    "overdue": [ ... ],
    "requests": [ ... ],
    "badge_counts": { "today": 3, "overdue": 1, "requests": 2 }
  }
}
```

---

#### `get_task_jobs`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_task_jobs`

**Request:** `{ "task": "TASK-0001" }`

**Response:** List of Jobs with their status, vehicle number, task type, and unread message count.

---

#### `respond_to_task`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.respond_to_task`

**Request:**
```json
{
  "task": "TASK-0001",
  "action": "accept",
  "reject_comment": null
}
```
(`action`: `"accept"` or `"reject"`)

---

#### `start_task`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.start_task`

**Request:** `{ "task": "TASK-0001" }`

**Notes:** Transitions task from Accepted → In Progress.

---

#### `get_job_types`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_job_types`

**Response:** All Task Type records: Installation, Checkup, Removal, Accessory.

---

#### `get_job`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_job`

**Request:** `{ "job": "JOB-2024-06-000001" }`

**Response:**
```json
{
  "message": {
    "name": "JOB-2024-06-000001",
    "status": "In Progress",
    "vehicle_number": "ABC1234",
    "task_type": "Installation",
    "customer": "General Motors",
    "item_installed_removed": {
      "Installed": [ { "item": "ITEM-001", "item_type": "GPS Device" } ],
      "Removed": []
    },
    "job_images": [ { "image": "/files/photo.jpg", "comment": "Front view" } ],
    "unread_count_tech": 2
  }
}
```

---

#### `get_job_item_options`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_job_item_options`

**Request:** `{ "job": "JOB-2024-06-000001", "direction": "Install" }`
(`direction`: `"Install"` — items from technician warehouse; `"Remove"` — items currently installed on vehicle)

**Response:** List of available items.

---

#### `get_vehicle_details`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_vehicle_details`

**Request:**
```json
{ "vehicle_number": "ABC1234", "task": "TASK-0001", "task_type": "Installation" }
```

**Notes:**
- Installation: vehicle must NOT already exist (creates new)
- Removal/Checkup/Accessory: vehicle must exist and customer must match task's customer

---

#### `create_job_for_task`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.create_job_for_task`

**Request:**
```json
{
  "task": "TASK-0001",
  "task_type": "Installation",
  "vehicle_number": "ABC1234",
  "make": "Toyota",
  "model": "Hilux",
  "type": "Truck",
  "color": "White",
  "items": [
    { "item": "ITEM-001", "installed_or_removed": "Installed" }
  ]
}
```

**Response:** `{"message": "JOB-2024-06-000001"}`

---

#### `update_job`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.update_job`

**Request:**
```json
{
  "job": "JOB-2024-06-000001",
  "items": [
    { "item": "ITEM-001", "installed_or_removed": "Installed" }
  ],
  "done_comment": null
}
```

**Notes:** `items` replaces all existing item rows. Posts "**Updated**" chat message automatically.

---

#### `upload_job_image`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.upload_job_image`

**Request (multipart or JSON):**
```json
{
  "job": "JOB-2024-06-000001",
  "image_data": "<base64_string>",
  "filename": "photo.jpg",
  "comment": "Installation complete"
}
```

**Response:** `{"message": { "name": "row_name", "image": "/files/photo.jpg", "comment": "..." }}`

---

#### `get_job_images`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.get_job_images`

**Request:** `{ "job": "JOB-2024-06-000001" }`

---

#### `delete_job_image`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.delete_job_image`

**Request:** `{ "job": "JOB-2024-06-000001", "row_name": "abc123" }`

---

#### `job_action`

**Endpoint:** `POST /api/method/fleet.mobile_api.tasks.job_action`

**Request:**
```json
{
  "job": "JOB-2024-06-000001",
  "action": "done",
  "comment": "Installed 2 GPS devices"
}
```

**Actions:**
| action | From → To | Requirements |
|---|---|---|
| `done` | In Progress → In Review | `comment` required + ≥1 job image |
| `hold` | In Progress → On Hold | — |
| `reopen` | On Hold → In Progress | — |

---

### 3.4 Chat APIs

#### `publish_job_chat`

**Endpoint:** `POST /api/method/fleet.api.dashboard_chat.publish_job_chat`

**Request:**
```json
{
  "job": "JOB-2024-06-000001",
  "message": "Please check the rear camera placement",
  "sender_name": "Support User",
  "role": "Support"
}
```

**Notes:** Increments unread counter; sends FCM push to technician.

#### `mark_messages_read`

**Endpoint:** `POST /api/method/fleet.api.dashboard_chat.mark_messages_read`

**Request:** `{ "job": "JOB-2024-06-000001", "reader_role": "Support" }`

#### `get_job_chat_messages`

**Endpoint:** `POST /api/method/fleet.api.dashboard_chat.get_job_chat_messages`

**Request:** `{ "job": "JOB-2024-06-000001", "limit": 50 }`

---

## 4. Production SOPs & Troubleshooting

### 4.1 Accessing Logs

**Frappe Error Logs (in-app):**
- **Path:** Desk → Error Log doctype  
- Filter by `method` or `title` to find specific errors.
- FCM errors are logged as "FCM: Send Failed" or "FCM: App Init Failed".

**File-based logs (Frappe Cloud):**
- Access via Frappe Cloud dashboard → Site → Logs
- `worker.error.log` — background job failures
- `worker.log` — general worker output
- `web.error.log` — HTTP request errors
- `scheduler.log` — scheduler and cron job output

### 4.2 Error Categories

| Category | Symptoms | Where to Look |
|---|---|---|
| Application | `ValidationError`, `frappe.throw()` | Frappe Error Log, browser console |
| Database | `OperationalError`, deadlocks, duplicate key | Frappe Error Log, MariaDB logs |
| Scheduler | Cron not running, tasks not auto-rejecting | scheduler.log, bench status |
| Permission | `PermissionError`, 403 responses | Error Log, permission settings |
| FCM / Firebase | Push not delivered | Error Log (title: "FCM:*"), Firebase Console |
| Infrastructure | 502/503, site down | Frappe Cloud dashboard, server logs |

### 4.3 Common Issues & Fixes

#### FCM Push Notifications Not Working

1. Go to **Firebase Settings** → verify `service_account_json` is valid JSON and not empty.
2. Check Error Log for entries with title starting "FCM:".
   - `FCM: App Init Failed` → service account JSON is invalid or missing.
   - `FCM: Send Failed` → token expired or invalid; user must log in again.
   - `FCM: No Token` → user has no registered FCM token; user must log in on mobile.
3. Verify `firebase-admin` is installed: on Frappe Cloud, check the deploy log for pip install output.

#### Data Import Fails for Vehicle

- **"Item X does not exist"** → Create the Item in the Item master first, then re-import.
- **"Item X is already Installed in vehicle Y"** → Mark the item as Removed on vehicle Y first.
- **Child table rows missing** → Usually license plate normalization issue (handled by code). Check if the plate was normalized correctly (spaces stripped, uppercased).

#### Technician Cannot Log In on Mobile

1. Verify the Employee has `designation = Technician` (not other).
2. Verify the linked User has the Technician role.
3. Verify `simultaneous_sessions = 1` on the User.

#### Task Not Auto-Rejected

1. Check if the bench scheduler is running: `bench status` or check Frappe Cloud scheduler status.
2. Look in scheduler.log for errors in `task_auto_reject`.
3. Verify the Task has `custom_assign_to` set and `custom_assigned_at` is populated.

#### Stock Entry Not Created on Job Completion

1. Check if a Stock Entry with `custom_job = {job_name}` already exists (idempotent guard — won't create duplicate).
2. Verify the technician warehouse has sufficient stock (`tabBin`).
3. Check Error Log for the Job name.

#### Warehouse Not Created for Customer

- Happens if `set_customer_warehouse` hook didn't fire (e.g. customer imported via Data Import without triggering after_insert).
- **Fix:** Open the Customer record and save it again (triggers `on_update` → creates warehouse if missing).

### 4.4 Escalation

| Issue | First Contact | Escalate To |
|---|---|---|
| Application bugs (code errors) | Development Team | — |
| Site down / infrastructure | Frappe Cloud Support | — |
| Database corruption / data loss | Frappe Cloud Support | Frappe Core Team |
| Firebase quota / delivery | Firebase Console | Google Firebase Support |

---

## 5. Customizations

### 5.1 Custom Fields

#### Task (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_customer` | Link→Customer | Customer this task belongs to |
| `custom_address` | Link→Address | Service location address |
| `custom_complete_address` | Small Text | Full formatted address (auto-filled) |
| `custom_latitude` / `custom_longitude` | Float | Coordinates for mobile map |
| `custom_assign_to` | Link→Employee | Assigned technician |
| `custom_assigned_at` | Datetime | When technician was assigned |
| `custom_employee_name` | Data | Technician name (fetch_from) |
| `custom_mobile_no` | Data | Technician mobile (fetch_from) |
| `custom_date` | Date | Service date |
| `custom_reject_comment` | Small Text | Rejection reason from technician |
| `custom_completed_by` | Link→User | Who completed the task |
| `custom_completed_on` | Datetime | When task was completed |
| `custom_task_jobs` | Table→Task Job | List of jobs in this task |
| `workflow_state` | Link→Workflow State | Current workflow state |

#### Vehicle (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_customer` | Link→Customer | Vehicle owner/customer |
| `custom_vehicle_item` | Table→Vehicle Item | Installed/removed items history |
| `custom_vehicle_type` | Select | Truck / Bus / Car / Mini Truck |

#### Item (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_item_type` | Link→Item Type | Type of fleet item (GPS Device, SIM, etc.) |
| `custom_current_warehouse` | Link→Warehouse | Where this item currently is |
| `custom_imei_no` | Data | IMEI number (GPS Device identifier) |
| `custom_serial_no` | Data | SIM serial number |
| `custom_mobile_number` | Data | Mobile number (SIM) |
| `custom_sim_type` | Select (Local/IOT) | SIM type |
| `custom_country_code` | Data | Country code (SIM) |
| `custom_activation_date` | Date | SIM activation date |
| `custom_sensor_unique_number` | Data | Fuel sensor identifier |
| `custom_temperature_serial_number` | Data | Temperature sensor identifier |
| `custom_dashcam_unique_number` | Data | Dashcam identifier |

#### Warehouse (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_customer_name` | Link→Customer | Which customer this warehouse belongs to |
| `custom_employee` | Link→Employee | Which technician this warehouse belongs to |

#### Address (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_latitude` | Float | GPS latitude |
| `custom_longitude` | Float | GPS longitude |
| `custom_location` | Geolocation | Map pin location |

#### Data Import (Frappe core doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_item_type` | Link→Item Type | Shared item type for all rows in batch |
| `custom_brand` | Link→Brand | Shared brand for batch |
| `custom_sim_type` | Select | Shared SIM type for batch |
| `custom_country_code` | Data | Shared country code for batch |

#### Stock Entry (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_job` | Data | Links stock entry to the job that created it |

#### Brand (ERPNext standard doctype)

| Field | Type | Purpose |
|---|---|---|
| `custom_item_type` | Link→Item Type | What item type this brand is for |

### 5.2 Custom DocTypes

#### Job (`fleet.fleet.doctype.job`)
Core work order doctype. Autoname: `JOB-.YYYY.-.MM.-.######`.  
Key fields: task, assigned_technician, vehicle_number, task_type, status, item_installed_removed (Table→Job Item), job_images (Table→Job Image), customer/technician warehouses, chat unread counts.

#### Material Transfer (`fleet.fleet.doctype.material_transfer`)
Submittable doctype for item transfers between warehouses. Autoname: `MT-.YYYY.-.MM.-.#####.`.  
Backed by a Workflow (Initiated → Approval Pending → Approved). On approval, creates ERPNext Stock Entry.

#### Task Job (`fleet.fleet.doctype.task_job`) — child table
Links a Task to its Jobs. Fields: job (Data), status, task_type (Link→Task Type), vehicle (Data).

#### Vehicle Item (`fleet.fleet.doctype.vehicle_item`) — child table
Item history for a Vehicle. Fields: item_type, status (Removed/Installed), item (Data), date.

#### Job Item (`fleet.fleet.doctype.job_item`) — child table
Items installed or removed in a Job. Fields: item (Link→Item), item_type, brand, installed_or_removed.

#### Job Image (`fleet.fleet.doctype.job_image`) — child table
Photo attachments for a Job. Fields: image (Attach), comment.

#### Job Message (`fleet.fleet.doctype.job_message`)
Chat messages between support and technician on a Job. Autoname: autoincrement.

#### Material Transfer Item (`fleet.fleet.doctype.material_transfer_item`) — child table

#### FCM Token (`fleet.fleet.doctype.fcm_token`)
Stores per-user FCM push notification token. One record per user (autoname: `field:user`).

#### Firebase Settings (`fleet.fleet.doctype.firebase_settings`)
Single doctype. Stores `service_account_json` (Firebase Admin SDK credentials JSON).

#### Item Type (`fleet.fleet.doctype.item_type`)
Master for item categories: GPS Device, SIM, Temperature, Fuel Sensor, Dashcam. Has `icon` field.

### 5.3 Hooks (`hooks.py`)

#### Document Events

| DocType | Event | Handler |
|---|---|---|
| User | validate | `user_warehouse_hooks.validate_user_roles` |
| User | on_update | `user_warehouse_hooks.on_update_user_roles` |
| Job | after_insert | `task_assignment.handle_job_assignment` |
| Job | on_update | `task_hooks.sync_job_status_to_row`, `task_assignment.handle_job_assignment` |
| Task | validate | `fleet.fleet.doctype.task.task.validate` |
| Task | on_update | `task.sync_vehicle_data`, `task_hooks.on_task_update`, `task_assignment.handle_assignment` |
| Employee | validate | `employee.validate_employee` |
| Employee | on_update | `employee.sync_user_with_employee` |
| Vehicle | validate | `vehicle.validate_vehicle` |
| Vehicle | after_insert | `vehicle.after_insert_vehicle` |
| Customer | after_insert / on_update / on_trash | `customer_warehouse.set_customer_warehouse` |
| Item | before_insert | `item.generate_item_details` |

#### Other Hooks

| Hook | Value |
|---|---|
| `override_doctype_class["Data Import"]` | `fleet.override.data_import.CustomDataImport` |
| `on_session_creation` | `fleet.mobile_api.auth.enforce_simultaneous_sessions` |
| `permission_query_conditions["Task"]` | `fleet.custom_py.permissions.task_permission_query` |
| `permission_query_conditions["Job"]` | `fleet.custom_py.permissions.job_permission_query` |
| `permission_query_conditions["Material Transfer"]` | `mt_permission_query` in material_transfer.py |
| `on_socket_event["join_job_room"]` | `fleet.override.job_chat.on_join_job_room` |
| `on_socket_event["leave_job_room"]` | `fleet.override.job_chat.on_leave_job_room` |

### 5.4 Server-Side Overrides

| File | What It Overrides |
|---|---|
| `override/customer_warehouse.py` | Auto-creates/manages Warehouse per Customer |
| `override/data_import.py` | `CustomDataImport` — stores shared item fields in Redis during Item Data Import |
| `override/item.py` | `generate_item_details` — builds item_code/item_name from IMEI/serial; sets initial warehouse |
| `override/task.py` | `sync_vehicle_data` — updates Vehicle records on Task completion |
| `override/job_chat.py` | WebSocket room handlers for real-time job chat |

### 5.5 Client Scripts (Public JS)

| File | DocType | Behaviour |
|---|---|---|
| `public/js/task.js` | Task | Action buttons per status, Add Jobs dialog, field locking |
| `public/js/task_list.js` | Task List | Real-time unread badge via WebSocket |
| `public/js/item.js` | Item | Item code generation, tracking timeline, barcode |
| `public/js/user.js` | User | Technician role guard, warehouse creation confirmation |
| `public/js/employee.js` | Employee | NRC mask, Change Password button |
| `public/js/address.js` | Address | Map integration with Nominatim reverse geocoding |
| `public/js/data_import.js` | Data Import | Clears fleet fields when doctype changes |
| `public/js/item_list.js` | Item List | Import Items button, real-time warehouse update |
| `public/js/customer_list.js` | Customer List | Import Customers button |
| `public/js/vehicle_list.js` | Vehicle List | Import Vehicles button |

### 5.6 Reports

| Report | Ref DocType | Roles | Purpose |
|---|---|---|---|
| Vehicle Item Warehouse Status | Vehicle | Fleet Administrator, Fleet Manager | Shows all Installed vehicle items vs customer warehouse; status: Correct/Mismatch/Item Not Found. Button: "Transfer All to Customer Warehouse" |
| Item Availability Report | Item | Fleet Administrator, Fleet Manager, Support Team | Shows all items with availability status (Available/Blocked by pending MT or active Job) |

### 5.7 Validations (Vehicle)

All run in `validate_vehicle` before save/import:

1. **License plate normalization** — spaces stripped, uppercased; becomes document `name` for new vehicles.
2. **Child row re-sync** — `custom_vehicle_item` rows' `parent` field updated to match normalized plate name (fixes Frappe Data Import order issue).
3. **Duplicate item+status dedup** — removes duplicate rows with the same `(item, status)` pair from `custom_vehicle_item`.
4. **Installed item existence check** — throws error if any "Installed" item does not exist in the Item master.
5. **Cross-vehicle conflict check** — throws error if any "Installed" item is already marked Installed on another Vehicle.

---

## 6. Contact / Escalation Matrix

| Issue Type | Owner | Action |
|---|---|---|
| Application bug / code error | Development Team | File issue / contact dev team |
| Site downtime / infrastructure | Frappe Cloud Support | Frappe Cloud dashboard → Support |
| Database issue / data corruption | Frappe Cloud Support | Frappe Cloud dashboard → Support |
| Firebase push notification delivery | Firebase Console / Google Support | Check Firebase Console delivery reports |
| User access / permission issue | System Administrator (in-app) | Manage roles in Frappe desk |
| Urgent production data fix | Development Team | Direct contact |

---

## 7. Scheduled / Background Jobs

### 7.1 Cron Jobs

| Schedule | Handler | What It Does |
|---|---|---|
| Every 5 minutes | `fleet.scheduled.task_auto_reject.auto_reject_unaccepted_tasks` | Finds Open tasks assigned to a technician for >1 hour without acceptance; auto-sets status=Rejected with a system comment |

### 7.2 Background Workers (Frappe default)

Frappe Cloud runs these automatically:

| Worker | Purpose |
|---|---|
| `default` worker | Handles in-app background jobs (report generation, email, etc.) |
| `short` worker | Short-running background tasks |
| `long` worker | Long-running background tasks (large data imports) |
| `schedule` worker | Triggers cron jobs from `scheduler_events` |

### 7.3 Real-time Events

| Event | Published By | Consumed By |
|---|---|---|
| `support_dashboard_new_message` | `job_message.py` after_insert | Support Dashboard — updates chat badge |
| `support_dashboard_read` | `dashboard_chat.mark_messages_read` | Support Dashboard — clears badge |
| `job_details_updated` | `mobile_api/tasks.py` | Support Dashboard Chat — updates cached job |
| `item_warehouse_updated` | `item_warehouse.py` | Item List — refreshes row |
| `task_job_chat_list_update` | (Task list) | Task List — updates unread dot |

---

## 8. Installed Apps & Dependencies

### 8.1 Frappe Apps

| App | Version | Branch | Role |
|---|---|---|---|
| `frappe` | 15.100.0 | version-15 | Core framework (ORM, REST API, auth, scheduler, WebSocket) |
| `erpnext` | 15.97.0 | version-15 | Business doctypes: Item, Warehouse, Customer, Employee, Task, Stock Entry, etc. |
| `pwa_frappe` | 1.0.2 | main | Progressive Web App support for mobile |
| `fleet` | 0.0.1 | you2 | This application |

### 8.2 Python Dependencies

Defined in `pyproject.toml`:

| Package | Version | Purpose |
|---|---|---|
| `firebase-admin` | `~=6.6.0` | Firebase Admin SDK for FCM push notifications |

### 8.3 System / APT Dependencies

| Package | Required For |
|---|---|
| `build-essential` | Compiling Python packages during deploy (required by firebase-admin) |

### 8.4 Runtime Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | `>=3.10` | Required by pyproject.toml |
| Node.js | 18.x | Frappe asset build |
| MariaDB | 10.6+ | Database |
| Redis | 6+ | Cache, queue, real-time |
| Frappe Bench | 5.x | Deployment tool |

---

## 9. External Integrations — Firebase FCM

### 9.1 Overview

Firebase Cloud Messaging (FCM) is used to send push notifications to the mobile app (technicians).

### 9.2 Configuration

1. Go to **Firebase Settings** doctype (single).
2. Paste the full Firebase Admin SDK service account JSON (from Google Cloud Console → Service Accounts).
3. The JSON is stored in `service_account_json` (Code field, JSON type).
4. Firebase App is initialized lazily per site with name `fleet_{site_name}`.

### 9.3 When Notifications Are Sent

| Trigger | Recipient | Title / Body |
|---|---|---|
| Task assigned to technician | Technician | New task assigned |
| Material Transfer submitted | Target warehouse users | Pending transfer approval |
| Material Transfer approved/rejected | Creator | Transfer result |
| Job chat message (Support → Technician) | Technician | Chat message |
| Job status changed | Support | Job status update |

### 9.4 FCM Token Management

- Token stored in `FCM Token` doctype (one per user, autoname = user email).
- Token saved on mobile login via `register_fcm_token`.
- Token deleted on logout via `delete_fcm_token`.
- Old tokens for the same `device_id` are replaced on re-login.

### 9.5 Error Handling

All FCM errors are logged to the Frappe **Error Log** with titles:
- `FCM: No Token` — user has no registered token (user not logged in on mobile)
- `FCM: App Init Failed` — service account JSON missing or invalid
- `FCM: Send Failed` — FCM API error (expired token, quota, etc.)

None of these errors crash the triggering operation — FCM failures are caught and logged silently.

---

## 10. Known Issues, Limitations & Workarounds

### 10.1 Known Issues

| Issue | Impact | Workaround |
|---|---|---|
| Vehicle Data Import requires items to exist in Item master first | Import fails with "Item X does not exist" if item codes are new | Create all Items via Item Data Import before Vehicle Data Import |
| Same item cannot be "Installed" in two vehicles simultaneously | Import/save blocked with validation error | Correct source data; mark item Removed on the old vehicle first |
| Customer Warehouse not created for customers imported via Data Import | `after_insert` hook doesn't fire during Data Import | Open each Customer and save manually after import to trigger warehouse creation |
| FCM push not delivered when Firebase credentials not configured | All mobile push notifications silently fail | Configure Firebase Settings immediately after site creation |
| `simultaneous_sessions = 1` on all technician users | Technician logged in on two devices — older session expires | By design; technicians are restricted to one active session |

### 10.2 Limitations

- **Material Transfer:** Only supports Technician → Technician or Technician → Store transfers. Store → Technician is handled by manual stock entry or initial item creation.
- **Vehicle license plate format:** Code strips spaces and uppercases. No format validation enforced beyond that (e.g. country-specific format validation not implemented).
- **Job item quantities:** All job items have implicit quantity of 1 — multiple units of the same item require separate rows.
- **No offline mode in mobile:** The mobile app requires an active internet connection. There is no offline queue for job actions.
- **Chat:** Chat is scoped per Job, not per Task. Support must open individual job chats to communicate with technicians.
- **Report data:** "Vehicle Item Warehouse Status" report has no date filter — shows current snapshot only.

### 10.3 Workarounds

| Situation | Workaround |
|---|---|
| Need to transfer item from Store to Technician | Create a manual ERPNext Material Transfer stock entry from desk (not via mobile) |
| Bulk fix item warehouse mismatches | Use "Transfer All to Customer Warehouse" button in Vehicle Item Warehouse Status report |
| Legacy vehicles need item warehouse update | Open Vehicle form → ensure customer set → save → items auto-transferred via `after_insert_vehicle` (only works if warehouse exists) |

---

## 11. Deployment & Migration Process

### 11.1 Frappe Cloud Deployment

**Trigger:** Push to the configured branch (default: `main`) on GitHub.

**Automated Steps (in order):**
1. **Clone** — Frappe Cloud clones the latest `fleet` app code from GitHub.
2. **APT Install** — Installs system packages from `[deploy.dependencies.apt]` in `pyproject.toml` (currently: `build-essential`).
3. **Pip Install** — Runs `pip install -e fleet` which installs Python dependencies from `[project] dependencies` (currently: `firebase-admin~=6.6.0`).
4. **Bench get-app** — App code is placed in the bench apps directory.
5. **Bench migrate** — Runs `bench migrate` which:
   - Syncs all DocType schemas (custom fields, new doctypes)
   - Syncs fixtures (roles, workflows, reports, etc.)
   - Runs any pending patches
   - Rebuilds assets if JS/CSS changed

### 11.2 Local Development Deployment

```bash
# Install app on an existing local site
cd /path/to/frappe-bench
bench get-app /path/to/fleet  # or git URL
bench --site {site_name} install-app fleet

# After code changes
bench --site {site_name} migrate

# Clear cache after JS changes
bench --site {site_name} clear-cache
bench build --app fleet
```

### 11.3 Migration Notes

- Migrations are **non-destructive** for schema changes (columns are added, never dropped automatically).
- Fixture sync is additive — existing records matching fixture filters are updated; others are untouched.
- The `firebase-admin` package requires `build-essential` for compilation — if APT dependencies are not installed, pip install will fail on Frappe Cloud.

### 11.4 Pre-Deployment Checklist

- [ ] Python syntax valid: `python3 -m py_compile fleet/**/*.py`
- [ ] JSON fixtures valid: validate with `python3 -m json.tool`
- [ ] JS syntax valid: `node --check file.js`
- [ ] `pyproject.toml` has both `[project] dependencies` and `[deploy.dependencies.apt]` sections if new system packages are needed
- [ ] No uncommitted changes to be left out of the PR
- [ ] Firebase Settings configured on target site

### 11.5 Rollback

Frappe Cloud supports deploy history — you can roll back to a previous deploy from the dashboard. This reverts app code only; database changes (migrations) are not automatically rolled back.

For database rollback: contact Frappe Cloud support to restore from a backup snapshot.

---

*Last updated: July 2026*
