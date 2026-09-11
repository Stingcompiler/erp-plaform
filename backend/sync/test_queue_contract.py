import uuid
from django.urls import reverse
from sales.models import Invoice
from sync.models import SyncBatch
from sync.tests import SyncBase


class QueueContractTests(SyncBase):
    def test_online_sale_replayed_offline_is_duplicate(self):
        self.push([self.movement_op(uuid.uuid4())])
        op = self.checkout_op(uuid.uuid4())
        online = self.client.post(reverse("pos-checkout"), op["payload"], format="json")
        self.assertEqual(online.status_code, 201, online.data)
        replay = self.push([op])
        self.assertEqual(replay.data["results"][0]["status"], "duplicate")
        self.assertEqual(Invoice.objects.count(), 1)

    def test_identity_mismatch_rejects_before_recording_any_batch(self):
        for key, value in [("expected_company", self.company.pk + 10),
                           ("expected_user", self.user.pk + 10), ("expected_branch", 9)]:
            response = self.client.post(reverse("sync-push"),
                                        {"batch_uuid": str(uuid.uuid4()),
                                         "operations": [self.movement_op(uuid.uuid4())],
                                         key: value,
                                         },
                                        format="json")
            self.assertEqual(response.status_code, 409)
        self.assertFalse(SyncBatch.objects.exists())

    def test_invalid_shapes_and_conflicting_identifiers_are_rejected(self):
        for ops in [[None], [{"payload": []}], [{"client_uuid": "bad", "payload": {}}]]:
            self.assertEqual(self.push(ops).status_code, 400)
        op = self.checkout_op(uuid.uuid4())
        op["payload"]["client_uuid"] = str(uuid.uuid4())
        self.assertEqual(self.push([op]).status_code, 400)
        self.assertFalse(SyncBatch.objects.exists())

    def test_partial_failure_has_individual_results_for_client_recovery(self):
        response = self.push([self.movement_op(uuid.uuid4()), {
                             "op_type": "unknown", "client_uuid": str(uuid.uuid4()),
                             "payload": {}}])
        self.assertEqual(response.status_code, 201)
        self.assertEqual([r["status"] for r in response.data["results"]], ["applied", "error"])
