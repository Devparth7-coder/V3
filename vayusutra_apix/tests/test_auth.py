"""
VayuSutra APIx - Authentication & RBAC Test Suite
Validates credentials, token generation, permission verification, and API auth endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from vayusutra_apix.api.main import app
from vayusutra_apix.auth.service import authenticate_user, get_demo_users, switch_user_role, PRE_SEEDED_USERS
from vayusutra_apix.auth.security import hash_password, verify_password, create_access_token, verify_access_token, check_has_permission
from vayusutra_apix.auth.models import UserRole


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_password_hashing_and_verification():
    """Verifies PBKDF2 password hashing produces unique salts and matches correctly."""
    pw = "SecretMoSPI2026!"
    h1, salt1 = hash_password(pw)
    h2, salt2 = hash_password(pw)
    
    assert h1 != h2  # Unique salt ensures different hashes
    assert salt1 != salt2
    assert verify_password(pw, h1, salt1) is True
    assert verify_password(pw, h2, salt2) is True
    assert verify_password("WrongPassword", h1, salt1) is False


def test_access_token_creation_and_verification():
    """Verifies HMAC signed tokens encode payload and reject tampering."""
    token = create_access_token("USR-TEST-01", "testuser", "test@gov.in", UserRole.MOSPI_ADMIN)
    assert token and "." in token
    
    payload = verify_access_token(token)
    assert payload is not None
    assert payload["uid"] == "USR-TEST-01"
    assert payload["usr"] == "testuser"
    assert payload["rol"] == UserRole.MOSPI_ADMIN.value

    # Tampered token check
    tampered = token[:-4] + "abcd"
    assert verify_access_token(tampered) is None


def test_pre_seeded_demo_users():
    """Verifies all 5 pre-configured government and admin roles are seeded."""
    demo_users = get_demo_users()
    assert len(demo_users) >= 5
    roles = [u.role for u in demo_users]
    assert UserRole.MOSPI_ADMIN in roles
    assert UserRole.RBI_MPC in roles
    assert UserRole.DGCA_REGULATOR in roles
    assert UserRole.SYSTEM_ADMIN in roles
    assert UserRole.PUBLIC_AUDITOR in roles


def test_authentication_workflow():
    """Verifies login for MoSPI, RBI, DGCA, and Admin with valid credentials."""
    # MoSPI
    res_mospi = authenticate_user("mospi@gov.in", "mospi2026!")
    assert res_mospi is not None
    assert res_mospi.user.role == UserRole.MOSPI_ADMIN
    assert "export_statutory" in res_mospi.user.permissions

    # RBI
    res_rbi = authenticate_user("rbi.mpc@rbi.org.in", "rbimpc2026!")
    assert res_rbi is not None
    assert res_rbi.user.role == UserRole.RBI_MPC
    assert "macro_stress_test" in res_rbi.user.permissions

    # DGCA
    res_dgca = authenticate_user("dgca.surveillance@dgca.nic.in", "dgca2026!")
    assert res_dgca is not None
    assert res_dgca.user.role == UserRole.DGCA_REGULATOR
    assert "inspect_corridors" in res_dgca.user.permissions

    # Admin
    res_admin = authenticate_user("admin@vayusutra.gov.in", "admin2026!")
    assert res_admin is not None
    assert res_admin.user.role == UserRole.SYSTEM_ADMIN
    assert "system_admin" in res_admin.user.permissions

    # Bad password
    res_fail = authenticate_user("admin@vayusutra.gov.in", "wrongpass")
    assert res_fail is None


def test_auth_api_endpoints(client):
    """Verifies REST API endpoints for auth, demo-users, login, me, and switch-role."""
    # 1. Demo users list
    res = client.get("/api/v1/auth/demo-users")
    assert res.status_code == 200
    data = res.json()
    assert "demo_accounts" in data
    assert len(data["demo_accounts"]) >= 5

    # 2. Login via API
    login_res = client.post("/api/v1/auth/login", json={
        "username_or_email": "mospi@gov.in",
        "password": "mospi2026!"
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    token = login_data["access_token"]
    assert login_data["user"]["role"] == "MOSPI_ADMIN"

    # 3. /me endpoint with Bearer token
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["email"] == "mospi@gov.in"

    # 4. Instant Demo Login endpoint
    demo_login_res = client.post("/api/v1/auth/demo-login/rbi")
    assert demo_login_res.status_code == 200
    assert demo_login_res.json()["user"]["role"] == "RBI_MPC"

    # 5. Roles list
    roles_res = client.get("/api/v1/auth/roles")
    assert roles_res.status_code == 200
    assert "roles" in roles_res.json()
