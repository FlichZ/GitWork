from django.test import TestCase, Client
from django.urls import reverse

class RestoreDBTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_restore_db_invalid_method(self):
        response = self.client.get(reverse('restore_db'))
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {
            "status": "error",
            "message": "Invalid request method"
        })

    def test_restore_db_success(self):
        with open('test_dump.sql', 'rb') as sql_file:
            response = self.client.post(reverse('restore_db'), {'file': sql_file})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            "status": "success",
            "message": "Database restored successfully"
        })






