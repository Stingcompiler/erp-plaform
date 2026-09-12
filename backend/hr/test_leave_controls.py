from datetime import date
from unittest.mock import patch

from django.urls import reverse

from core.models import ActivityLog
from hr.models import Attendance, LeaveRequest
from hr.tests import HrBase


class LeaveControlTests(HrBase):
    def payload(self, **changes):
        return {'employee': self.emp_a.pk, 'start_date': '2026-09-10', 'end_date': '2026-09-12', **changes}

    def create_leave(self):
        response = self.client.post(reverse('leaverequest-list'), self.payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def test_crud_cannot_decide_leave(self):
        self.assertEqual(self.client.post(reverse('leaverequest-list'), self.payload(status='approved'), format='json').status_code, 400)
        pk = self.create_leave()
        for method in (self.client.patch, self.client.put):
            self.assertEqual(method(reverse('leaverequest-detail', args=[pk]), self.payload(status='approved'), format='json').status_code, 400)
        self.assertEqual(LeaveRequest.objects.get(pk=pk).status, 'pending')
        self.assertEqual(Attendance.objects.count(), 0)

    def test_overlap_rejected_and_adjacent_dates_allowed(self):
        self.create_leave()
        self.assertEqual(self.client.post(reverse('leaverequest-list'), self.payload(start_date='2026-09-12', end_date='2026-09-14'), format='json').status_code, 400)
        self.assertEqual(self.client.post(reverse('leaverequest-list'), self.payload(start_date='2026-09-13', end_date='2026-09-14'), format='json').status_code, 201)

    def test_approved_leave_locked_and_retry_is_idempotent(self):
        pk = self.create_leave()
        approve_url = reverse('leaverequest-approve', args=[pk])
        self.assertEqual(self.client.post(approve_url).status_code, 200)
        reviewed = LeaveRequest.objects.get(pk=pk).reviewed_at
        self.assertEqual(self.client.post(approve_url).status_code, 200)
        self.assertEqual(LeaveRequest.objects.get(pk=pk).reviewed_at, reviewed)
        self.assertEqual(self.client.patch(reverse('leaverequest-detail', args=[pk]), {'end_date': '2026-09-15'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(reverse('leaverequest-detail', args=[pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse('leaverequest-reject', args=[pk])).status_code, 400)
        self.assertEqual(Attendance.objects.filter(employee=self.emp_a, status='leave').count(), 3)
        self.assertEqual(ActivityLog.objects.filter(entity_type='LeaveRequest', entity_id=str(pk), action='approve').count(), 1)

    def test_failed_attendance_sync_rolls_back_approval(self):
        pk = self.create_leave()
        with patch('hr.views.apply_approved_leave', side_effect=RuntimeError('simulated failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('leaverequest-approve', args=[pk]))
        leave = LeaveRequest.objects.get(pk=pk)
        self.assertEqual(leave.status, 'pending')
        self.assertIsNone(leave.reviewed_at)
        self.assertFalse(ActivityLog.objects.filter(entity_type='LeaveRequest', entity_id=str(pk), action='approve').exists())

    def test_conflicting_attendance_blocks_approval(self):
        pk = self.create_leave()
        Attendance.objects.create(company=self.company_a, employee=self.emp_a, date=date(2026, 9, 11), status='present')
        self.assertEqual(self.client.post(reverse('leaverequest-approve', args=[pk])).status_code, 400)
        self.assertEqual(LeaveRequest.objects.get(pk=pk).status, 'pending')

    def test_pending_edit_and_withdrawal_still_work(self):
        pk = self.create_leave()
        self.assertEqual(self.client.patch(reverse('leaverequest-detail', args=[pk]), {'reason': 'Updated'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(reverse('leaverequest-detail', args=[pk])).status_code, 204)

    def test_rejected_leave_does_not_block_replacement(self):
        pk = self.create_leave()
        self.assertEqual(self.client.post(reverse('leaverequest-reject', args=[pk])).status_code, 200)
        self.create_leave()

    def test_invalid_employment_and_other_company_rejected(self):
        self.emp_a.hire_date = date(2026, 10, 1)
        self.emp_a.save()
        self.assertEqual(self.client.post(reverse('leaverequest-list'), self.payload(), format='json').status_code, 400)
        self.assertEqual(self.client.post(reverse('leaverequest-list'), self.payload(employee=self.emp_b.pk), format='json').status_code, 400)
