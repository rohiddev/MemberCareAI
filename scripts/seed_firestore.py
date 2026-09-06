from membercare_app.config.firestore import get_firestore_client


def seed_data():
    db = get_firestore_client()

    # ========================================================
    # MEMBER
    # ========================================================

    member = {
        "member_id": "MEM-001",
        "first_name": "Alex",
        "last_name": "Morgan",
        "plan_id": "PLAN-001",
        "status": "ACTIVE",
    }

    db.collection("members").document("MEM-001").set(member)

    # ========================================================
    # BENEFIT PLAN
    # ========================================================

    plan = {
        "plan_id": "PLAN-001",
        "plan_name": "Choice Plus Gold",
        "plan_type": "PPO",
        "individual_deductible": 1500.00,
        "coinsurance_percent": 20,
        "active": True,
    }

    db.collection("plans").document("PLAN-001").set(plan)

    # ========================================================
    # PROVIDER
    # ========================================================

    provider = {
        "provider_id": "PRV-001",
        "provider_name": "Valley Imaging Center",
        "specialty": "Diagnostic Imaging",
        "network_status": "IN_NETWORK",
        "active": True,
    }

    db.collection("providers").document("PRV-001").set(provider)

    # ========================================================
    # CLAIM
    # ========================================================

    claim = {
        "claim_id": "CLM-10001",
        "member_id": "MEM-001",
        "provider_id": "PRV-001",
        "plan_id": "PLAN-001",
        "service_type": "MRI",
        "status": "PAID",
        "billed_amount": 1400.00,
        "allowed_amount": 850.00,
        "plan_paid": 680.00,
        "member_responsibility": 170.00,
    }

    db.collection("claims").document("CLM-10001").set(claim)

    print("Seed data written successfully.")
    print("Member:   MEM-001")
    print("Plan:     PLAN-001")
    print("Provider: PRV-001")
    print("Claim:    CLM-10001")


if __name__ == "__main__":
    seed_data()
