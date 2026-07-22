"""Task-related pydantic models + shared vocabulary.

Designed forward-compatible for procurement / PO / inventory / vendor
payments integration (added task doc fields never mutate: `procurement_link`,
`po_id`, `inventory_id`, `vendor_payment_status`).
"""
from pydantic import BaseModel
from typing import List, Optional


# ---------- Vocabulary ----------
TASK_LANES = ["todo", "in_progress", "review", "done"]

TASK_TYPES = ["employee", "vendor"]

TASK_STATUS_DETAIL = [
    "Pending", "Selection Required", "Reference Required", "Vendor Required",
    "Quotation Requested", "Quotation Received", "Ordered",
    "Work Started", "In Progress", "On Hold",
    "Inspection Pending", "Completed", "Cancelled",
]

TASK_PRIORITIES = ["low", "medium", "high", "urgent", "critical"]

STATUS_TO_LANE = {
    "Pending": "todo", "Selection Required": "todo", "Reference Required": "todo",
    "Vendor Required": "todo", "Quotation Requested": "todo",
    "Quotation Received": "in_progress", "Ordered": "in_progress",
    "Work Started": "in_progress", "In Progress": "in_progress",
    "On Hold": "review", "Inspection Pending": "review",
    "Completed": "done", "Cancelled": "done",
}

LANE_TO_DEFAULT_STATUS = {
    "todo": "Pending",
    "in_progress": "In Progress",
    "review": "Inspection Pending",
    "done": "Completed",
}

DEFAULT_AREAS = [
    "Entrance", "Foyer", "Living Room", "Drawing Room", "Dining Room", "Kitchen",
    "Utility", "Store Room", "Pooja Room", "Parents Bedroom", "Master Bedroom",
    "Kids Bedroom", "Guest Bedroom", "Walk-in Closet",
    "Master Bathroom", "Common Bathroom", "Powder Room", "Balcony", "Terrace",
    "Home Office", "Study Room", "Family Lounge", "Staircase",
    "Basement", "Parking", "Garden", "Outdoor Area",
]

DEFAULT_CATEGORIES_EMPLOYEE = [
    "2D Drawing", "3D Design", "BOQ", "Site Visit", "Client Meeting",
    "Material Selection", "Estimation", "Working Drawings",
    "Concept Design", "Presentation", "Approval", "Coordination",
]

DEFAULT_CATEGORIES_VENDOR = [
    "Carpenter", "Painter", "Electrician", "Plumber",
    "Marble Contractor", "Fabricator", "False Ceiling",
    "Hardware Vendor", "Furniture Vendor", "Decor Vendor",
    "Lighting Vendor", "Curtain Vendor", "Wallpaper Vendor",
    "AC / HVAC", "Automation", "Kitchen Vendor", "Wardrobe Vendor",
    "Tile Vendor", "Glass / Mirror", "Landscaping",
]

DEFAULT_CATEGORIES = sorted(set(DEFAULT_CATEGORIES_EMPLOYEE + DEFAULT_CATEGORIES_VENDOR))

REMINDER_FREQUENCIES = ["one_time", "daily", "weekly", "monthly", "custom"]

# Timeline event constants (helps future analytics)
TIMELINE_EVENTS = {
    "CREATED": "created",
    "UPDATED": "updated",
    "STATUS_CHANGED": "status_changed",
    "ASSIGNED": "assigned",
    "FOLLOW_UP_ADDED": "follow_up_added",
    "FOLLOW_UP_UPDATED": "follow_up_updated",
    "ATTACHMENT_ADDED": "attachment_added",
    "COMMENT_ADDED": "comment_added",
    "COMPLETED": "completed",
}


# ---------- Pydantic ----------
class VendorContact(BaseModel):
    vendor_name: Optional[str] = ""
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    whatsapp: Optional[str] = ""
    company_name: Optional[str] = ""
    address: Optional[str] = ""


class Attachment(BaseModel):
    label: Optional[str] = ""
    url: str
    type: Optional[str] = "link"    # link | image | pdf | doc


class FollowUpIn(BaseModel):
    follow_up_date: Optional[str] = None
    reminder_date: Optional[str] = None
    reminder_time: Optional[str] = None
    reminder_frequency: Optional[str] = "one_time"
    assigned_employee: Optional[str] = None
    assigned_employee_name: Optional[str] = None
    notes: Optional[str] = ""
    status: Optional[str] = "pending"     # pending | done | skipped
    next_follow_up_date: Optional[str] = None
    attachments: Optional[List[Attachment]] = None


class TaskIn(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    task_type: Optional[str] = "employee"   # employee | vendor
    area: Optional[str] = None
    category: Optional[str] = None
    item_description: Optional[str] = None
    quantity: Optional[float] = None
    priority: Optional[str] = "medium"
    status: Optional[str] = "todo"          # kanban lane (auto-derived if status_detail set)
    status_detail: Optional[str] = None     # granular
    remarks: Optional[str] = None
    reference_links: Optional[List[str]] = None
    attachments: Optional[List[Attachment]] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    assignees: Optional[List[str]] = None
    vendor_id: Optional[str] = None           # FK → vendors_acc (primary link)
    vendor_contact: Optional[VendorContact] = None
    due_date: Optional[str] = None
    follow_up_date: Optional[str] = None
    reminder_date: Optional[str] = None
    reminder_time: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    task_type: Optional[str] = None
    area: Optional[str] = None
    category: Optional[str] = None
    item_description: Optional[str] = None
    quantity: Optional[float] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    status_detail: Optional[str] = None
    remarks: Optional[str] = None
    reference_links: Optional[List[str]] = None
    attachments: Optional[List[Attachment]] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    assignees: Optional[List[str]] = None
    vendor_id: Optional[str] = None           # FK → vendors_acc
    vendor_contact: Optional[VendorContact] = None
    due_date: Optional[str] = None
    follow_up_date: Optional[str] = None
    reminder_date: Optional[str] = None
    reminder_time: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: Optional[str] = None          # lane
    status_detail: Optional[str] = None   # granular


class BulkUpdateIn(BaseModel):
    task_ids: List[str]
    status: Optional[str] = None
    status_detail: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    area: Optional[str] = None
    category: Optional[str] = None


class CustomAreaIn(BaseModel):
    name: str


class CustomCategoryIn(BaseModel):
    name: str
    task_type: Optional[str] = None   # optional filter tag
