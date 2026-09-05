"""
Design Saga API Tests
Tests for CRM, Projects, Tasks, Clients, Invoices, Client Portal, AI Assistant
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
AUTH_TOKEN = "test_session_admin_001"
HEADERS = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}


class TestAuthEndpoints:
    """Authentication endpoint tests"""
    
    def test_auth_me_with_valid_token(self):
        """GET /api/auth/me with valid bearer token returns user"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert data["email"] == "admin@designsaga.test"
        assert data["role"] == "admin"
        print(f"Auth/me passed: user={data['email']}, role={data['role']}")
    
    def test_auth_me_without_token(self):
        """GET /api/auth/me without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401


class TestSeedEndpoint:
    """Seed demo data endpoint tests"""
    
    def test_seed_creates_demo_data(self):
        """POST /api/seed creates demo data"""
        response = requests.post(f"{BASE_URL}/api/seed", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        assert "projects" in data
        assert "leads" in data
        assert "tasks" in data
        assert "invoices" in data
        print(f"Seed passed: projects={data['projects']}, leads={data['leads']}, tasks={data['tasks']}, invoices={data['invoices']}")


class TestDashboardEndpoints:
    """Dashboard stats endpoint tests"""
    
    def test_dashboard_stats(self):
        """GET /api/dashboard/stats returns kpis, pipeline, alerts, utilization, sources"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        
        # Check KPIs
        assert "kpis" in data
        kpis = data["kpis"]
        assert "revenue" in kpis
        assert "active_projects" in kpis
        assert "total_projects" in kpis
        assert "overdue_tasks" in kpis
        assert "collection_due" in kpis
        
        # Check pipeline (6 stages)
        assert "pipeline" in data
        pipeline = data["pipeline"]
        assert len(pipeline) == 6
        stages = [p["stage"] for p in pipeline]
        assert "New" in stages
        assert "Won" in stages
        assert "Lost" in stages
        
        # Check alerts
        assert "alerts" in data
        
        # Check utilization
        assert "utilization" in data
        
        # Check sources
        assert "sources" in data
        
        print(f"Dashboard stats passed: kpis={kpis}, pipeline_stages={len(pipeline)}")


class TestLeadsCRUD:
    """Leads (CRM) CRUD tests"""
    
    def test_list_leads(self):
        """GET /api/leads returns list of leads"""
        response = requests.get(f"{BASE_URL}/api/leads", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"List leads passed: count={len(data)}")
    
    def test_create_lead(self):
        """POST /api/leads creates a new lead"""
        payload = {
            "name": "TEST_Lead_API",
            "email": "test_lead@example.com",
            "phone": "+91 98765 00000",
            "source": "Website",
            "project_type": "Residential",
            "budget": 1500000,
            "location": "Mumbai",
            "stage": "New"
        }
        response = requests.post(f"{BASE_URL}/api/leads", json=payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Lead_API"
        assert data["email"] == "test_lead@example.com"
        assert "id" in data
        print(f"Create lead passed: id={data['id']}")
        return data["id"]
    
    def test_update_lead_stage(self):
        """PATCH /api/leads/{id}/stage updates lead stage"""
        # First create a lead
        create_payload = {"name": "TEST_Lead_Stage", "source": "Referral", "stage": "New"}
        create_resp = requests.post(f"{BASE_URL}/api/leads", json=create_payload, headers=HEADERS)
        assert create_resp.status_code == 200
        lead_id = create_resp.json()["id"]
        
        # Update stage
        update_payload = {"stage": "Qualified"}
        response = requests.patch(f"{BASE_URL}/api/leads/{lead_id}/stage", json=update_payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "Qualified"
        print(f"Update lead stage passed: id={lead_id}, new_stage={data['stage']}")
    
    def test_delete_lead(self):
        """DELETE /api/leads/{id} deletes a lead"""
        # First create a lead
        create_payload = {"name": "TEST_Lead_Delete", "source": "Walk-in", "stage": "New"}
        create_resp = requests.post(f"{BASE_URL}/api/leads", json=create_payload, headers=HEADERS)
        lead_id = create_resp.json()["id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/leads/{lead_id}", headers=HEADERS)
        assert response.status_code == 200
        assert response.json().get("ok") == True
        
        # Verify deleted - list should not contain this lead
        list_resp = requests.get(f"{BASE_URL}/api/leads", headers=HEADERS)
        leads = list_resp.json()
        lead_ids = [l["id"] for l in leads]
        assert lead_id not in lead_ids
        print(f"Delete lead passed: id={lead_id}")
    
    def test_convert_lead_to_project(self):
        """POST /api/leads/{id}/convert creates project + client"""
        # Create a lead
        create_payload = {
            "name": "TEST_Lead_Convert",
            "email": "convert@example.com",
            "phone": "+91 99999 00000",
            "source": "Instagram",
            "project_type": "Commercial",
            "budget": 2500000,
            "location": "Bangalore",
            "stage": "Negotiation"
        }
        create_resp = requests.post(f"{BASE_URL}/api/leads", json=create_payload, headers=HEADERS)
        lead_id = create_resp.json()["id"]
        
        # Convert
        response = requests.post(f"{BASE_URL}/api/leads/{lead_id}/convert", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "project_id" in data
        assert "client_id" in data
        print(f"Convert lead passed: lead_id={lead_id}, project_id={data['project_id']}, client_id={data['client_id']}")


class TestProjectsCRUD:
    """Projects CRUD tests"""
    
    def test_list_projects(self):
        """GET /api/projects returns list of projects"""
        response = requests.get(f"{BASE_URL}/api/projects", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"List projects passed: count={len(data)}")
    
    def test_create_project(self):
        """POST /api/projects creates a new project"""
        payload = {
            "name": "TEST_Project_API",
            "project_type": "Residential",
            "budget": 3000000,
            "stage": "Concept",
            "description": "Test project created via API"
        }
        response = requests.post(f"{BASE_URL}/api/projects", json=payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Project_API"
        assert "id" in data
        assert "share_token" in data
        print(f"Create project passed: id={data['id']}, share_token={data['share_token']}")
        return data
    
    def test_get_project_detail(self):
        """GET /api/projects/{id} returns project with tasks/files/invoices"""
        # First create a project
        create_payload = {"name": "TEST_Project_Detail", "project_type": "Commercial", "stage": "Requirement"}
        create_resp = requests.post(f"{BASE_URL}/api/projects", json=create_payload, headers=HEADERS)
        project_id = create_resp.json()["id"]
        
        # Get detail
        response = requests.get(f"{BASE_URL}/api/projects/{project_id}", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert "tasks" in data
        assert "files" in data
        assert "invoices" in data
        assert "milestones" in data
        print(f"Get project detail passed: id={project_id}, tasks={len(data['tasks'])}, files={len(data['files'])}")
    
    def test_update_project_stage(self):
        """PATCH /api/projects/{id}/stage updates project stage"""
        # Create project
        create_payload = {"name": "TEST_Project_Stage", "stage": "Requirement"}
        create_resp = requests.post(f"{BASE_URL}/api/projects", json=create_payload, headers=HEADERS)
        project_id = create_resp.json()["id"]
        
        # Update stage
        update_payload = {"stage": "Design Dev"}
        response = requests.patch(f"{BASE_URL}/api/projects/{project_id}/stage", json=update_payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "Design Dev"
        print(f"Update project stage passed: id={project_id}, new_stage={data['stage']}")
    
    def test_delete_project(self):
        """DELETE /api/projects/{id} deletes a project"""
        # Create project
        create_payload = {"name": "TEST_Project_Delete", "stage": "Requirement"}
        create_resp = requests.post(f"{BASE_URL}/api/projects", json=create_payload, headers=HEADERS)
        project_id = create_resp.json()["id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/projects/{project_id}", headers=HEADERS)
        assert response.status_code == 200
        assert response.json().get("ok") == True
        print(f"Delete project passed: id={project_id}")


class TestTasksCRUD:
    """Tasks CRUD tests"""
    
    def test_list_tasks(self):
        """GET /api/tasks returns list of tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"List tasks passed: count={len(data)}")
    
    def test_list_tasks_with_project_filter(self):
        """GET /api/tasks?project_id= filters by project"""
        # Get a project first
        projects_resp = requests.get(f"{BASE_URL}/api/projects", headers=HEADERS)
        projects = projects_resp.json()
        if projects:
            project_id = projects[0]["id"]
            response = requests.get(f"{BASE_URL}/api/tasks?project_id={project_id}", headers=HEADERS)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # All tasks should belong to this project
            for task in data:
                assert task.get("project_id") == project_id
            print(f"List tasks with filter passed: project_id={project_id}, count={len(data)}")
    
    def test_create_task(self):
        """POST /api/tasks creates a new task"""
        payload = {
            "title": "TEST_Task_API",
            "description": "Test task created via API",
            "priority": "high",
            "status": "todo",
            "due_date": "2026-04-30"
        }
        response = requests.post(f"{BASE_URL}/api/tasks", json=payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Task_API"
        assert data["priority"] == "high"
        assert "id" in data
        print(f"Create task passed: id={data['id']}")
    
    def test_update_task_status(self):
        """PATCH /api/tasks/{id}/status updates task status"""
        # Create task
        create_payload = {"title": "TEST_Task_Status", "status": "todo"}
        create_resp = requests.post(f"{BASE_URL}/api/tasks", json=create_payload, headers=HEADERS)
        task_id = create_resp.json()["id"]
        
        # Update status
        update_payload = {"status": "in_progress"}
        response = requests.patch(f"{BASE_URL}/api/tasks/{task_id}/status", json=update_payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        print(f"Update task status passed: id={task_id}, new_status={data['status']}")
    
    def test_delete_task(self):
        """DELETE /api/tasks/{id} deletes a task"""
        # Create task
        create_payload = {"title": "TEST_Task_Delete", "status": "todo"}
        create_resp = requests.post(f"{BASE_URL}/api/tasks", json=create_payload, headers=HEADERS)
        task_id = create_resp.json()["id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=HEADERS)
        assert response.status_code == 200
        assert response.json().get("ok") == True
        print(f"Delete task passed: id={task_id}")


class TestClientsCRUD:
    """Clients CRUD tests"""
    
    def test_list_clients(self):
        """GET /api/clients returns list of clients"""
        response = requests.get(f"{BASE_URL}/api/clients", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"List clients passed: count={len(data)}")
    
    def test_create_client(self):
        """POST /api/clients creates a new client"""
        payload = {
            "name": "TEST_Client_API",
            "email": "test_client@example.com",
            "phone": "+91 98765 11111",
            "company": "Test Company",
            "address": "Test Address, Mumbai"
        }
        response = requests.post(f"{BASE_URL}/api/clients", json=payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Client_API"
        assert data["email"] == "test_client@example.com"
        assert "id" in data
        print(f"Create client passed: id={data['id']}")


class TestInvoicesCRUD:
    """Invoices/Quotations CRUD tests"""
    
    def test_list_invoices(self):
        """GET /api/invoices?doc_type=invoice returns invoices"""
        response = requests.get(f"{BASE_URL}/api/invoices?doc_type=invoice", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for inv in data:
            assert inv.get("doc_type") == "invoice"
        print(f"List invoices passed: count={len(data)}")
    
    def test_list_quotations(self):
        """GET /api/invoices?doc_type=quotation returns quotations"""
        response = requests.get(f"{BASE_URL}/api/invoices?doc_type=quotation", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for inv in data:
            assert inv.get("doc_type") == "quotation"
        print(f"List quotations passed: count={len(data)}")
    
    def test_create_invoice_with_items(self):
        """POST /api/invoices with items creates invoice"""
        payload = {
            "client_name": "TEST_Invoice_Client",
            "items": [
                {"description": "Design consultation", "quantity": 1, "rate": 50000, "amount": 50000},
                {"description": "3D renders", "quantity": 5, "rate": 10000, "amount": 50000}
            ],
            "tax_rate": 18,
            "notes": "Test invoice notes",
            "due_date": "2026-05-15",
            "status": "draft",
            "doc_type": "invoice"
        }
        response = requests.post(f"{BASE_URL}/api/invoices", json=payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "number" in data
        assert data["number"].startswith("INV-")
        assert data["subtotal"] == 100000
        assert data["tax"] == 18000
        assert data["total"] == 118000
        print(f"Create invoice passed: id={data['id']}, number={data['number']}, total={data['total']}")
        return data["id"]
    
    def test_update_invoice_status(self):
        """PATCH /api/invoices/{id}/status updates invoice status"""
        # Create invoice
        create_payload = {
            "client_name": "TEST_Invoice_Status",
            "items": [{"description": "Test item", "quantity": 1, "rate": 10000, "amount": 10000}],
            "tax_rate": 0,
            "status": "draft",
            "doc_type": "invoice"
        }
        create_resp = requests.post(f"{BASE_URL}/api/invoices", json=create_payload, headers=HEADERS)
        invoice_id = create_resp.json()["id"]
        
        # Update status
        update_payload = {"status": "sent"}
        response = requests.patch(f"{BASE_URL}/api/invoices/{invoice_id}/status", json=update_payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        print(f"Update invoice status passed: id={invoice_id}, new_status={data['status']}")
    
    def test_delete_invoice(self):
        """DELETE /api/invoices/{id} deletes an invoice"""
        # Create invoice
        create_payload = {
            "client_name": "TEST_Invoice_Delete",
            "items": [{"description": "Delete test", "quantity": 1, "rate": 5000, "amount": 5000}],
            "tax_rate": 0,
            "status": "draft",
            "doc_type": "invoice"
        }
        create_resp = requests.post(f"{BASE_URL}/api/invoices", json=create_payload, headers=HEADERS)
        invoice_id = create_resp.json()["id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/invoices/{invoice_id}", headers=HEADERS)
        assert response.status_code == 200
        assert response.json().get("ok") == True
        print(f"Delete invoice passed: id={invoice_id}")
    
    def test_invoice_pdf_generation(self):
        """GET /api/invoices/{id}/pdf returns valid PDF binary"""
        # Create invoice
        create_payload = {
            "client_name": "TEST_PDF_Client",
            "items": [{"description": "PDF test item", "quantity": 2, "rate": 25000, "amount": 50000}],
            "tax_rate": 18,
            "notes": "PDF generation test",
            "status": "draft",
            "doc_type": "invoice"
        }
        create_resp = requests.post(f"{BASE_URL}/api/invoices", json=create_payload, headers=HEADERS)
        invoice_id = create_resp.json()["id"]
        
        # Get PDF
        response = requests.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf", headers=HEADERS)
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        # Check PDF magic bytes
        assert response.content[:4] == b'%PDF'
        print(f"Invoice PDF generation passed: id={invoice_id}, size={len(response.content)} bytes")


class TestClientPortal:
    """Client portal (no-auth) tests"""
    
    def test_portal_view(self):
        """GET /api/portal/{share_token} returns project with progress, tasks, files, invoices"""
        # Get a project with share_token
        projects_resp = requests.get(f"{BASE_URL}/api/projects", headers=HEADERS)
        projects = projects_resp.json()
        project_with_token = None
        for p in projects:
            if p.get("share_token"):
                project_with_token = p
                break
        
        if not project_with_token:
            pytest.skip("No project with share_token found")
        
        share_token = project_with_token["share_token"]
        
        # Access portal without auth
        response = requests.get(f"{BASE_URL}/api/portal/{share_token}")
        assert response.status_code == 200
        data = response.json()
        
        # Check project info
        assert "project" in data
        project = data["project"]
        assert "progress" in project
        assert "all_stages" in project
        assert len(project["all_stages"]) == 9  # 9 project stages
        
        # Check tasks summary
        assert "tasks_summary" in data
        assert "total" in data["tasks_summary"]
        assert "done" in data["tasks_summary"]
        assert "in_progress" in data["tasks_summary"]
        
        # Check files and invoices
        assert "files" in data
        assert "invoices" in data
        
        print(f"Portal view passed: share_token={share_token}, progress={project['progress']}%")
    
    def test_portal_message(self):
        """POST /api/portal/{token}/message sends a message"""
        # Get a project with share_token
        projects_resp = requests.get(f"{BASE_URL}/api/projects", headers=HEADERS)
        projects = projects_resp.json()
        project_with_token = None
        for p in projects:
            if p.get("share_token"):
                project_with_token = p
                break
        
        if not project_with_token:
            pytest.skip("No project with share_token found")
        
        share_token = project_with_token["share_token"]
        
        # Send message without auth
        payload = {
            "from_name": "Test Client",
            "message": "This is a test message from the client portal"
        }
        response = requests.post(f"{BASE_URL}/api/portal/{share_token}/message", json=payload)
        assert response.status_code == 200
        assert response.json().get("ok") == True
        print(f"Portal message passed: share_token={share_token}")
    
    def test_portal_invalid_token(self):
        """GET /api/portal/{invalid_token} returns 404"""
        response = requests.get(f"{BASE_URL}/api/portal/invalid_token_12345")
        assert response.status_code == 404


class TestAIAssistant:
    """AI Assistant (Claude Sonnet 4.5) tests"""
    
    def test_ai_chat(self):
        """POST /api/ai/chat with message returns response + session_id"""
        payload = {
            "message": "What projects are currently active?"
        }
        response = requests.post(f"{BASE_URL}/api/ai/chat", json=payload, headers=HEADERS, timeout=60)
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "session_id" in data
        assert len(data["response"]) > 0
        print(f"AI chat passed: session_id={data['session_id']}, response_length={len(data['response'])}")
        return data["session_id"]
    
    def test_ai_history(self):
        """GET /api/ai/history/{session_id} returns persisted messages"""
        # First send a message to create history
        chat_payload = {"message": "List all leads"}
        chat_resp = requests.post(f"{BASE_URL}/api/ai/chat", json=chat_payload, headers=HEADERS, timeout=60)
        session_id = chat_resp.json()["session_id"]
        
        # Get history
        response = requests.get(f"{BASE_URL}/api/ai/history/{session_id}", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # At least user message + assistant response
        
        # Check message structure
        roles = [m["role"] for m in data]
        assert "user" in roles
        assert "assistant" in roles
        print(f"AI history passed: session_id={session_id}, messages={len(data)}")


class TestFilesEndpoints:
    """Files endpoints tests"""
    
    def test_list_files(self):
        """GET /api/files returns list of files"""
        response = requests.get(f"{BASE_URL}/api/files", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"List files passed: count={len(data)}")
    
    def test_create_file(self):
        """POST /api/files creates a file link"""
        # Get a project first
        projects_resp = requests.get(f"{BASE_URL}/api/projects", headers=HEADERS)
        projects = projects_resp.json()
        if not projects:
            pytest.skip("No projects found")
        
        project_id = projects[0]["id"]
        payload = {
            "project_id": project_id,
            "name": "TEST_File_API.pdf",
            "url": "https://example.com/test-file.pdf",
            "stage": "Concept",
            "version": 1
        }
        response = requests.post(f"{BASE_URL}/api/files", json=payload, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_File_API.pdf"
        assert "id" in data
        print(f"Create file passed: id={data['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
