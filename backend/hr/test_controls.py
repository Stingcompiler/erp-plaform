from datetime import date
from django.urls import reverse
from accounts.models import Role, User
from core.models import ActivityLog
from hr.models import Employee, PayrollRun, SalaryAdvance
from hr.tests import HrBase


class HrControlTests(HrBase):
    def owner(self):
        role = Role.objects.create(name='Business Owner', scope_level=Role.SCOPE_BUSINESS)
        user = User.objects.create_user(email='owner@alpha.test', password='test', company=self.company_a, role=role)
        self.client.force_authenticate(user)

    def test_advance_status_cannot_be_written_through_crud(self):
        response = self.client.post(reverse('salaryadvance-list'), {'employee': self.emp_a.pk, 'amount': '100', 'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, 400)
        advance = SalaryAdvance.objects.create(company=self.company_a, employee=self.emp_a, amount=100)
        for method in (self.client.patch, self.client.put):
            response = method(reverse('salaryadvance-detail', args=[advance.pk]), {'employee': self.emp_a.pk, 'amount': '100', 'status': 'approved'}, format='json')
            self.assertEqual(response.status_code, 400)
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'pending')

    def test_decided_advance_is_locked_and_retry_does_not_retimestamp(self):
        advance = SalaryAdvance.objects.create(company=self.company_a, employee=self.emp_a, amount=100)
        self.owner()
        url = reverse('salaryadvance-approve', args=[advance.pk])
        self.assertEqual(self.client.post(url).status_code, 200)
        advance.refresh_from_db()
        reviewed = advance.reviewed_at
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(reverse('salaryadvance-reject', args=[advance.pk])).status_code, 400)
        self.assertEqual(self.client.patch(reverse('salaryadvance-detail', args=[advance.pk]), {'amount': '200'}, format='json').status_code, 400)
        advance.refresh_from_db()
        self.assertEqual(advance.reviewed_at, reviewed)
        self.assertEqual(advance.amount, 100)

    def test_payroll_cannot_be_deleted_and_actions_are_audited(self):
        response = self.client.post(reverse('payrollrun-list'), {'period': '2026-09'}, format='json')
        self.assertEqual(response.status_code, 201)
        pk = response.data['id']
        self.assertEqual(self.client.post(reverse('payrollrun-refresh', args=[pk])).status_code, 200)
        self.owner()
        self.assertEqual(self.client.post(reverse('payrollrun-approve', args=[pk])).status_code, 200)
        self.assertEqual(self.client.delete(reverse('payrollrun-detail', args=[pk])).status_code, 405)
        self.assertTrue(PayrollRun.objects.filter(pk=pk, status='approved').exists())
        self.assertEqual(set(ActivityLog.objects.filter(entity_type='PayrollRun', entity_id=str(pk)).values_list('action', flat=True)), {'create', 'recalculate', 'approve'})

    def test_branch_manager_cannot_read_payroll(self):
        role = Role.objects.create(name='Branch Manager', scope_level=Role.SCOPE_BRANCH)
        user = User.objects.create_user(email='branch@alpha.test', password='test', company=self.company_a, role=role)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse('payrollrun-list')).status_code, 403)

    def test_future_hire_excluded_and_refresh_returns_current_values(self):
        Employee.objects.create(company=self.company_a, full_name='Future', hire_date=date(2027, 1, 1))
        response = self.client.post(reverse('payrollrun-list'), {'period': '2026-09'}, format='json')
        self.assertEqual(response.data['employee_count'], 1)
        self.emp_a.base_salary_override = 1700
        self.emp_a.save()
        response = self.client.post(reverse('payrollrun-refresh', args=[response.data['id']]))
        self.assertEqual(response.data['entries'][0]['base_salary'], '1700.00')

    def test_negative_salary_rejected(self):
        self.assertEqual(self.client.patch(reverse('employee-detail', args=[self.emp_a.pk]), {'base_salary_override': '-1'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(reverse('position-detail', args=[self.pos_a.pk]), {'base_salary': '-1'}, format='json').status_code, 400)

    def test_cross_company_payroll_hidden(self):
        run = PayrollRun.objects.create(company=self.company_b, period=date(2026, 9, 1))
        self.assertEqual(self.client.get(reverse('payrollrun-detail', args=[run.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('payrollrun-refresh', args=[run.pk])).status_code, 404)
