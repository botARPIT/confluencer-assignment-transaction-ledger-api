from decimal import Decimal

from fastapi.testclient import TestClient


def test_ledger_history_validation_and_atomic_transfer(client: TestClient) -> None:
    source_response = client.post("/accounts", json={"name": "Ada Lovelace"})
    destination_response = client.post("/accounts", json={"name": "Grace Hopper"})
    assert source_response.status_code == 201
    assert destination_response.status_code == 201
    source_id = source_response.json()["id"]
    destination_id = destination_response.json()["id"]
    assert source_response.json()["balance"] == "0.00"
    assert destination_response.json()["balance"] == "0.00"

    balance_response = client.get(f"/accounts/{source_id}")
    assert balance_response.json() == {"account_id": source_id, "balance": "0.00"}
    assert client.post("/accounts", json={"name": "Ada", "balance": "500.00"}).status_code == 422

    credit_body = {
        "type": "credit", "amount": "75.25", "description": "Paycheck", "reference_id": "credit-1",
    }
    assert client.post(f"/accounts/{source_id}/transactions", json=credit_body).status_code == 201
    debit_response = client.post(f"/accounts/{source_id}/transactions", json={
        "type": "debit", "amount": "20.25", "description": "Coffee", "reference_id": "debit-1",
    })
    assert debit_response.status_code == 201

    paged = client.get(f"/accounts/{source_id}/transactions?page=1&limit=1").json()
    assert paged["page"] == 1
    assert paged["limit"] == 1
    assert paged["total_records"] == 2
    assert paged["total_pages"] == 2
    assert len(paged["transactions"]) == 1
    credits = client.get(f"/accounts/{source_id}/transactions?type=credit").json()
    assert credits["total_records"] == 1
    assert credits["transactions"][0]["reference_id"] == "credit-1"

    assert client.post(f"/accounts/{source_id}/transactions", json=credit_body).status_code == 409
    assert client.get(f"/accounts/{source_id}").json()["balance"] == "55.00"
    assert client.post(f"/accounts/{source_id}/transactions", json={
        "type": "debit", "amount": "55.01", "description": "Too much", "reference_id": "overdraw-1",
    }).status_code == 409
    assert client.get(f"/accounts/{source_id}/transactions").json()["total_records"] == 2

    transfer_body = {
        "source_account_id": source_id,
        "destination_account_id": destination_id,
        "amount": "15.00",
        "description": "Repayment",
        "reference_id": "transfer-1",
    }
    transfer_response = client.post("/transfers", json=transfer_body)
    assert transfer_response.status_code == 201
    assert transfer_response.json()["source_balance"] == "40.00"
    assert transfer_response.json()["destination_balance"] == "15.00"
    assert client.get(f"/accounts/{source_id}/transactions?type=debit").json()["total_records"] == 2
    assert client.get(f"/accounts/{destination_id}/transactions?type=credit").json()["total_records"] == 1

    failed_transfer = {**transfer_body, "amount": "100.00", "reference_id": "transfer-2"}
    assert client.post("/transfers", json=failed_transfer).status_code == 409
    assert Decimal(client.get(f"/accounts/{source_id}").json()["balance"]) == Decimal("40.00")
    assert Decimal(client.get(f"/accounts/{destination_id}").json()["balance"]) == Decimal("15.00")
    assert client.get(f"/accounts/{source_id}/transactions").json()["total_records"] == 3
    assert client.get(f"/accounts/{destination_id}/transactions").json()["total_records"] == 1
