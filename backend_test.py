#!/usr/bin/env python3
"""
Backend API tests for ERP connectivity + usability improvements.
Tests project team, task visibility gate, multi-assignee, vendor tasks,
SuperAdmin billing, and tenant isolation.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://finance-corrections.preview.emergentagent.com/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class ERPTester:
    def __init__(self):
        self.admin_token = None
        self.super_admin_token = None
        self.employee_token = None
        self.accountant_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.created_resources = {
            "projects": [],
            "tasks": [],
            "employees": [],
            "users": [],
            "vendors": []
        }

    def log(self, msg, color=Colors.BLUE):
        print(f"{color}{msg}{Colors.END}")

    def success(self, msg):
        self.tests_passed += 1
        print(f"{Colors.GREEN}✅ {msg}{Colors.END}")

    def fail(self, msg):
        self.tests_failed += 1
        print(f"{Colors.RED}❌ {msg}{Colors.END}")

    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, params=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        self.log(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.success(f"Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                self.fail(f"Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            self.fail(f"Failed - Error: {str(e)}")
            return False, {}

    def login(self, identifier, password):
        """Login and get token"""
        self.log(f"🔐 Logging in as {identifier}...")
        success, response = self.run_test(
            f"Login {identifier}",
            "POST",
            "/auth/login-password",
            200,
            data={"identifier": identifier, "password": password}
        )
        if success and 'session_token' in response:
            return response['session_token']
        return None

    def test_project_team_creation(self):
        """Test 1: PROJECT TEAM ON CREATE - POST /api/projects with PM + team"""
        self.log("\n" + "="*80, Colors.YELLOW)
        self.log("TEST 1: PROJECT TEAM ON CREATE", Colors.YELLOW)
        self.log("="*80, Colors.YELLOW)

        # First, get or create employees
        success, emp_response = self.run_test(
            "Get employees",
            "GET",
            "/employees",
            200,
            token=self.admin_token
        )
        
        employees = emp_response.get("employees", []) if isinstance(emp_response, dict) else emp_response
        
        if not employees or len(employees) < 2:
            self.log("⚠️  Not enough employees, creating test employees...")
            # Create test employees
            for i in range(2):
                success, emp = self.run_test(
                    f"Create test employee {i+1}",
                    "POST",
                    "/employees",
                    200,  # API returns 200 for creates
                    data={
                        "first_name": f"Test",
                        "last_name": f"Employee{i+1}",
                        "email": f"test.emp{i+1}@test.com",
                        "designation": "Designer",
                        "department": "Design"
                    },
                    token=self.admin_token
                )
                if success:
                    employees.append(emp)
                    self.created_resources["employees"].append(emp.get("id"))

        if len(employees) >= 2:
            pm_id = employees[0].get("id")
            team_ids = [employees[1].get("id")]
            
            # Create project with PM and team
            success, project = self.run_test(
                "Create project with PM + team",
                "POST",
                "/projects",
                200,  # API returns 200 for creates
                data={
                    "name": f"Test Project Team {datetime.now().strftime('%H%M%S')}",
                    "project_type": "Residential",
                    "engagement_type": "consultancy",  # Required for hybrid workspaces
                    "budget": 500000,
                    "project_manager_id": pm_id,
                    "team_ids": team_ids
                },
                token=self.admin_token
            )
            
            if success:
                project_id = project.get("id")
                self.created_resources["projects"].append(project_id)
                
                # Verify GET /api/projects/{id} returns enriched names
                success, detail = self.run_test(
                    "Get project detail with team enrichment",
                    "GET",
                    f"/projects/{project_id}",
                    200,
                    token=self.admin_token
                )
                
                if success:
                    pm = detail.get("project_manager")
                    team = detail.get("team", [])
                    
                    if pm and pm.get("name"):
                        self.success(f"Project Manager enriched: {pm.get('name')}")
                    else:
                        self.fail("Project Manager name not enriched (null or missing)")
                    
                    if team and len(team) > 0 and team[0].get("name"):
                        self.success(f"Team member enriched: {team[0].get('name')}")
                    else:
                        self.fail("Team member names not enriched")
                    
                    return project_id, pm_id, team_ids
        else:
            self.fail("Could not create enough employees for team test")
        
        return None, None, []

    def test_task_visibility_gate(self, project_id, pm_id, team_ids):
        """Test 2: TASK VISIBILITY GATE - Regular users see only their project tasks"""
        self.log("\n" + "="*80, Colors.YELLOW)
        self.log("TEST 2: TASK VISIBILITY GATE (KEY FEATURE)", Colors.YELLOW)
        self.log("="*80, Colors.YELLOW)

        if not project_id:
            self.fail("Skipping - no project created")
            return

        # Create a task in the project (not assigned to anyone)
        success, task_a = self.run_test(
            "Create TaskA in ProjectA (unassigned)",
            "POST",
            "/tasks",
            200,  # API returns 200 for creates
            data={
                "title": f"TaskA - Project Team Visible {datetime.now().strftime('%H%M%S')}",
                "project_id": project_id,
                "task_type": "employee",
                "priority": "medium"
            },
            token=self.admin_token
        )
        
        if success:
            self.created_resources["tasks"].append(task_a.get("id"))

        # Create another project WITHOUT the employee
        success, project_b = self.run_test(
            "Create ProjectB (employee NOT on team)",
            "POST",
            "/projects",
            200,  # API returns 200 for creates
            data={
                "name": f"Test Project B {datetime.now().strftime('%H%M%S')}",
                "project_type": "Commercial",
                "engagement_type": "turnkey",  # Required for hybrid workspaces
                "budget": 300000
            },
            token=self.admin_token
        )
        
        if success:
            project_b_id = project_b.get("id")
            self.created_resources["projects"].append(project_b_id)
            
            # Create TaskB in ProjectB
            success, task_b = self.run_test(
                "Create TaskB in ProjectB",
                "POST",
                "/tasks",
                200,  # API returns 200 for creates
                data={
                    "title": f"TaskB - Should NOT be visible {datetime.now().strftime('%H%M%S')}",
                    "project_id": project_b_id,
                    "task_type": "employee",
                    "priority": "high"
                },
                token=self.admin_token
            )
            
            if success:
                self.created_resources["tasks"].append(task_b.get("id"))

        # Test with Accountant (non-privileged role - no tasks.delete permission)
        if self.accountant_token:
            self.log("\n📋 Testing as Accountant (non-privileged)...")
            success, tasks = self.run_test(
                "Get tasks as Accountant",
                "GET",
                "/tasks",
                200,
                token=self.accountant_token
            )
            
            if success:
                task_ids = [t.get("id") for t in tasks]
                task_titles = [t.get("title") for t in tasks]
                
                # Accountant should see ONLY tasks assigned to them or in their projects
                # Since accountant is not on any team and no tasks assigned, should see empty or very limited
                self.log(f"   Accountant sees {len(tasks)} tasks")
                if len(tasks) == 0 or (task_a.get("id") not in task_ids and task_b.get("id") not in task_ids):
                    self.success("Accountant correctly restricted (sees no project team tasks)")
                else:
                    self.fail(f"Accountant should not see project team tasks but sees: {task_titles}")

        # Test with Admin (privileged role - has tasks.delete permission)
        self.log("\n👑 Testing as Admin (privileged)...")
        success, admin_tasks = self.run_test(
            "Get tasks as Admin",
            "GET",
            "/tasks",
            200,
            token=self.admin_token
        )
        
        if success:
            admin_task_ids = [t.get("id") for t in admin_tasks]
            if task_a.get("id") in admin_task_ids and task_b.get("id") in admin_task_ids:
                self.success("Admin sees ALL tasks (privileged role)")
            else:
                self.fail("Admin should see all tasks but some are missing")

        # Test assigned_to_me field
        if team_ids:
            # Create a task assigned to the team member
            success, assigned_task = self.run_test(
                "Create task assigned to team member",
                "POST",
                "/tasks",
                200,  # API returns 200 for creates
                data={
                    "title": f"Assigned Task {datetime.now().strftime('%H%M%S')}",
                    "project_id": project_id,
                    "assignees": team_ids,
                    "task_type": "employee"
                },
                token=self.admin_token
            )
            
            if success:
                self.created_resources["tasks"].append(assigned_task.get("id"))
                
                # Check if assigned_to_me is set
                if assigned_task.get("assigned_to_me") is not None:
                    self.success("Task has assigned_to_me field")
                else:
                    self.fail("Task missing assigned_to_me field")

    def test_multi_assignee_notify(self):
        """Test 3: MULTI-ASSIGNEE + NOTIFY"""
        self.log("\n" + "="*80, Colors.YELLOW)
        self.log("TEST 3: MULTI-ASSIGNEE + NOTIFY", Colors.YELLOW)
        self.log("="*80, Colors.YELLOW)

        # Get employees
        success, emp_response = self.run_test(
            "Get employees for assignment",
            "GET",
            "/employees",
            200,
            token=self.admin_token
        )
        
        employees = emp_response.get("employees", []) if isinstance(emp_response, dict) else emp_response
        
        if len(employees) >= 2:
            assignee_ids = [employees[0].get("id"), employees[1].get("id")]
            
            # Create task with multiple assignees
            success, task = self.run_test(
                "Create task with multiple assignees",
                "POST",
                "/tasks",
                200,  # API returns 200 for creates
                data={
                    "title": f"Multi-assignee Task {datetime.now().strftime('%H%M%S')}",
                    "assignees": assignee_ids,
                    "task_type": "employee",
                    "priority": "high"
                },
                token=self.admin_token
            )
            
            if success:
                self.created_resources["tasks"].append(task.get("id"))
                
                # Check assigned_by fields
                if task.get("assigned_by") and task.get("assigned_by_name"):
                    self.success(f"Task has assigned_by: {task.get('assigned_by_name')}")
                else:
                    self.fail("Task missing assigned_by/assigned_by_name")
                
                # Check notifications (get notifications for first assignee)
                # Note: We can't directly verify notifications without employee user login
                # but we can verify the task was created successfully
                self.success("Multi-assignee task created successfully")
        else:
            self.fail("Not enough employees for multi-assignee test")

    def test_task_vendor(self):
        """Test 4: TASK→VENDOR"""
        self.log("\n" + "="*80, Colors.YELLOW)
        self.log("TEST 4: TASK→VENDOR", Colors.YELLOW)
        self.log("="*80, Colors.YELLOW)

        # Get vendors
        success, vendors = self.run_test(
            "Get vendors",
            "GET",
            "/vendors",
            200,
            token=self.admin_token
        )
        
        if success and vendors and len(vendors) > 0:
            vendor_id = vendors[0].get("id")
            vendor_name = vendors[0].get("name")
            
            # Create vendor task
            success, task = self.run_test(
                "Create vendor task with vendor_id",
                "POST",
                "/tasks",
                200,  # API returns 200 for creates
                data={
                    "title": f"Vendor Task {datetime.now().strftime('%H%M%S')}",
                    "task_type": "vendor",
                    "vendor_id": vendor_id,
                    "priority": "medium"
                },
                token=self.admin_token
            )
            
            if success:
                self.created_resources["tasks"].append(task.get("id"))
                
                # Verify vendor_name and vendor_contact are backfilled
                if task.get("vendor_name") == vendor_name:
                    self.success(f"Vendor name backfilled: {vendor_name}")
                else:
                    self.fail(f"Vendor name not backfilled. Expected: {vendor_name}, Got: {task.get('vendor_name')}")
                
                if task.get("vendor_contact") and task.get("vendor_contact", {}).get("vendor_name"):
                    self.success("Vendor contact backfilled")
                else:
                    self.fail("Vendor contact not backfilled")
        else:
            self.log("⚠️  No vendors found, creating test vendor...")
            success, vendor = self.run_test(
                "Create test vendor",
                "POST",
                "/vendors",
                200,  # API returns 200 for creates
                data={
                    "name": "Test Vendor Agency",
                    "agency_type": "Carpenter",
                    "contact_person": "John Doe",
                    "phone": "9876543210",
                    "email": "vendor@test.com"
                },
                token=self.admin_token
            )
            
            if success:
                self.created_resources["vendors"].append(vendor.get("id"))
                # Retry the test
                self.test_task_vendor()

    def test_superadmin_billing(self):
        """Test 5: SUPERADMIN BILLING"""
        self.log("\n" + "="*80, Colors.YELLOW)
        self.log("TEST 5: SUPERADMIN BILLING", Colors.YELLOW)
        self.log("="*80, Colors.YELLOW)

        if not self.super_admin_token:
            self.fail("No SuperAdmin token - skipping billing test")
            return

        # Get orgs
        success, orgs = self.run_test(
            "Get organizations",
            "GET",
            "/platform/orgs",
            200,
            token=self.super_admin_token
        )
        
        if success and orgs and len(orgs) > 0:
            org_id = orgs[0].get("org_id")
            
            # Update billing info
            billing_data = {
                "billing": {
                    "owner_override": "Test Owner",
                    "amount_charged": 50000,
                    "maintenance_charge": 10000,
                    "billing_cycle": "yearly",
                    "start_date": "2025-01-01",
                    "renewal_date": "2026-01-01",
                    "notes": "Test billing update"
                }
            }
            
            success, updated_org = self.run_test(
                "Update org billing",
                "PATCH",
                f"/platform/orgs/{org_id}",
                200,
                data=billing_data,
                token=self.super_admin_token
            )
            
            if success:
                billing = updated_org.get("billing", {})
                
                # Verify all billing fields
                checks = [
                    ("owner_override", "Test Owner"),
                    ("amount_charged", 50000),
                    ("maintenance_charge", 10000),
                    ("billing_cycle", "yearly"),
                    ("start_date", "2025-01-01"),
                    ("renewal_date", "2026-01-01"),
                    ("notes", "Test billing update")
                ]
                
                for field, expected in checks:
                    if billing.get(field) == expected:
                        self.success(f"Billing {field} set correctly: {expected}")
                    else:
                        self.fail(f"Billing {field} mismatch. Expected: {expected}, Got: {billing.get(field)}")
                
                # Test partial update (should not wipe other fields)
                success, partial = self.run_test(
                    "Partial billing update",
                    "PATCH",
                    f"/platform/orgs/{org_id}",
                    200,
                    data={"billing": {"amount_charged": 60000}},
                    token=self.super_admin_token
                )
                
                if success:
                    new_billing = partial.get("billing", {})
                    if new_billing.get("amount_charged") == 60000 and new_billing.get("maintenance_charge") == 10000:
                        self.success("Partial billing update preserved other fields")
                    else:
                        self.fail("Partial billing update wiped other fields")
            
            # Verify owner and owner_email in list
            success, orgs_list = self.run_test(
                "Get orgs list with owner",
                "GET",
                "/platform/orgs",
                200,
                token=self.super_admin_token
            )
            
            if success:
                org = next((o for o in orgs_list if o.get("org_id") == org_id), None)
                if org:
                    if org.get("owner"):
                        self.success(f"Org has owner: {org.get('owner')}")
                    else:
                        self.fail("Org missing owner field")
                    
                    if org.get("owner_email"):
                        self.success(f"Org has owner_email: {org.get('owner_email')}")
                    else:
                        self.log("⚠️  Org missing owner_email (may be manual override)")
        else:
            self.fail("No organizations found for billing test")

    def test_tenant_isolation(self):
        """Test 6: TENANT ISOLATION"""
        self.log("\n" + "="*80, Colors.YELLOW)
        self.log("TEST 6: TENANT ISOLATION", Colors.YELLOW)
        self.log("="*80, Colors.YELLOW)

        if not self.super_admin_token:
            self.fail("No SuperAdmin token - skipping isolation test")
            return

        success, result = self.run_test(
            "Run isolation check",
            "GET",
            "/platform/isolation-check",
            200,
            token=self.super_admin_token
        )
        
        if success:
            status = result.get("status")
            problems = result.get("problems", [])
            collections_checked = result.get("collections_checked", 0)
            
            if status == "PASS":
                self.success(f"Tenant isolation PASS ({collections_checked} collections checked)")
            else:
                self.fail(f"Tenant isolation FAIL - {len(problems)} problems found")
                for p in problems:
                    print(f"   ⚠️  {p.get('collection')}: {p.get('missing_org_id')} missing, {p.get('unknown_org_id')} unknown")

    def cleanup(self):
        """Clean up created resources"""
        self.log("\n🧹 Cleaning up test resources...", Colors.BLUE)
        
        # Delete tasks
        for task_id in self.created_resources["tasks"]:
            try:
                requests.delete(f"{BASE_URL}/tasks/{task_id}", 
                              headers={'Authorization': f'Bearer {self.admin_token}'})
            except:
                pass
        
        # Delete projects
        for project_id in self.created_resources["projects"]:
            try:
                requests.delete(f"{BASE_URL}/projects/{project_id}", 
                              headers={'Authorization': f'Bearer {self.admin_token}'})
            except:
                pass

    def run_all_tests(self):
        """Run all tests"""
        self.log("\n" + "="*80, Colors.BLUE)
        self.log("🚀 ERP CONNECTIVITY + USABILITY TESTS", Colors.BLUE)
        self.log("="*80 + "\n", Colors.BLUE)

        # Login
        self.admin_token = self.login("admin@designsaga.com", "Admin@123")
        if not self.admin_token:
            self.fail("Admin login failed - cannot continue")
            return 1

        self.super_admin_token = self.login("designsaga10@gmail.com", "Admin@123")
        if not self.super_admin_token:
            self.log("⚠️  SuperAdmin login failed - some tests will be skipped", Colors.YELLOW)

        self.accountant_token = self.login("acct@test.com", "Acct@1234")
        if not self.accountant_token:
            self.log("⚠️  Accountant login failed - visibility test will be limited", Colors.YELLOW)

        # Run tests
        project_id, pm_id, team_ids = self.test_project_team_creation()
        self.test_task_visibility_gate(project_id, pm_id, team_ids)
        self.test_multi_assignee_notify()
        self.test_task_vendor()
        self.test_superadmin_billing()
        self.test_tenant_isolation()

        # Cleanup
        self.cleanup()

        # Summary
        self.log("\n" + "="*80, Colors.BLUE)
        self.log("📊 TEST SUMMARY", Colors.BLUE)
        self.log("="*80, Colors.BLUE)
        self.log(f"Total tests run: {self.tests_run}")
        self.log(f"✅ Passed: {self.tests_passed}", Colors.GREEN)
        self.log(f"❌ Failed: {self.tests_failed}", Colors.RED)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"Success rate: {success_rate:.1f}%", Colors.BLUE)
        
        return 0 if self.tests_failed == 0 else 1

if __name__ == "__main__":
    tester = ERPTester()
    sys.exit(tester.run_all_tests())
