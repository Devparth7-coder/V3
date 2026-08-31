"""
VayuSutra APIx - Authentication Service & User Repository
User management, pre-seeded executive credentials, and session handlers.
"""

import datetime
import sqlite3
import hashlib
import json
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Header, Depends, status, Request
from ..config.db import get_db_connection
from .models import User, UserRole, DemoUserCredential, LoginResponse
from .security import hash_password, verify_password, create_access_token, verify_access_token, check_has_permission, get_permissions_for_role


PRE_SEEDED_USERS = [
    {
        "user_id": "USR-MOSPI-01",
        "username": "mospi_admin",
        "email": "mospi@gov.in",
        "raw_password": "mospi2026!",
        "full_name": "Dr. Arvind Sharma",
        "role": UserRole.MOSPI_ADMIN,
        "designation": "Joint Director, Price Statistics Division",
        "organization": "MoSPI / National Statistical Office (NSO)",
        "department": "Economic Statistics & Price Indices",
        "avatar_color": "#10b981",  # Emerald Green
        "badge_theme": "emerald",
        "description": "Ministry of Statistics & PI - Headline CPI, eSankhyiki catalog baseline, and Transport Group 6.1.03 price indexes.",
        "key_features": ["MoSPI eSankhyiki Sync", "Statutory CSV Export", "Jevons/Laspeyres/Fisher Decomposer", "CPI Pass-Through Analysis"]
    },
    {
        "user_id": "USR-RBI-01",
        "username": "rbi_mpc",
        "email": "rbi.mpc@rbi.org.in",
        "raw_password": "rbimpc2026!",
        "full_name": "Smt. Radhika Iyer",
        "role": UserRole.RBI_MPC,
        "designation": "Senior Monetary Policy Advisor & MPC Head",
        "organization": "Reserve Bank of India (RBI)",
        "department": "Monetary Policy & Macroeconomic Research",
        "avatar_color": "#818cf8",  # Royal Indigo/Purple
        "badge_theme": "indigo",
        "description": "Reserve Bank of India - Monetary Policy formulation, inflation nowcasting, and macroeconomic shock simulations.",
        "key_features": ["Policy What-If Simulator", "Forward Inflation Fan Chart (95% CI)", "Basis Point Transmission Gauge", "Rate Decision Guidance"]
    },
    {
        "user_id": "USR-DGCA-01",
        "username": "dgca_regulator",
        "email": "dgca.surveillance@dgca.nic.in",
        "raw_password": "dgca2026!",
        "full_name": "Capt. Vikram Malhotra",
        "role": UserRole.DGCA_REGULATOR,
        "designation": "Director of Air Transport Surveillance & Tariff Monitoring",
        "organization": "Directorate General of Civil Aviation (DGCA)",
        "department": "Air Transport Regulatory Wing",
        "avatar_color": "#f59e0b",  # Amber / Gold
        "badge_theme": "amber",
        "description": "Civil Aviation Authority - Route volatility monitoring, surge pricing inspection, carrier dispersion, and consumer fare safeguards.",
        "key_features": ["20x5 Airfare Heatmap Matrix", "Route Surge Anomaly Detector", "Carrier Price Dispersion", "Lead-Time Elasticity Curve"]
    },
    {
        "user_id": "USR-ADMIN-01",
        "username": "admin",
        "email": "admin@vayusutra.gov.in",
        "raw_password": "admin2026!",
        "full_name": "Dev Parth and Team VayuSutra",
        "role": UserRole.SYSTEM_ADMIN,
        "designation": "Principal System Architect & Lead Econometric Engineer",
        "organization": "VayuSutra Command & Engineering",
        "department": "National Infrastructure & Data Engineering",
        "avatar_color": "#38bdf8",  # Cyan Blue
        "badge_theme": "cyan",
        "description": "Full Root Administrative Access - Background worker daemons, model retraining, rate limiter metrics, and cryptographic ledger vault.",
        "key_features": ["Full Subsystem Clearance", "60s Worker Daemon Controls", "ML Nowcast Model Retraining", "Cryptographic Provenance Vault"]
    },
    {
        "user_id": "USR-AUDIT-01",
        "username": "guest_auditor",
        "email": "auditor@sih2026.gov.in",
        "raw_password": "guest2026!",
        "full_name": "Academic Peer Reviewer & Public Auditor",
        "role": UserRole.PUBLIC_AUDITOR,
        "designation": "Independent Statistical Audit Fellow",
        "organization": "SIH2026 / Academic Peer Review Consortium",
        "department": "Public Statistical Transparency",
        "avatar_color": "#94a3b8",  # Slate
        "badge_theme": "slate",
        "description": "Public Transparency & Verification - Read-only access with SHA-256 quote trace inspection and methodology validation.",
        "key_features": ["SHA-256 Quote Trace Audit", "Mathematical Formula Proofs", "Open Datasets Explorer", "35-Day Backtesting Metrics"]
    }
]


def init_auth_tables():
    """Initializes users and sessions tables in database and populates pre-seeded users."""
    conn = get_db_connection()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL,
                designation TEXT NOT NULL,
                organization TEXT NOT NULL,
                department TEXT NOT NULL,
                avatar_color TEXT NOT NULL DEFAULT '#38bdf8',
                is_active INTEGER NOT NULL DEFAULT 1,
                last_login_at TEXT,
                created_at TEXT NOT NULL
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)

        # Check and insert pre-seeded users
        for u in PRE_SEEDED_USERS:
            existing = conn.execute("SELECT user_id FROM users WHERE user_id = ? OR email = ?", (u["user_id"], u["email"])).fetchone()
            if not existing:
                pw_hash, salt = hash_password(u["raw_password"])
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                conn.execute("""
                    INSERT INTO users (
                        user_id, username, email, full_name, password_hash, password_salt,
                        role, designation, organization, department, avatar_color,
                        is_active, last_login_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
                """, (
                    u["user_id"], u["username"], u["email"], u["full_name"],
                    pw_hash, salt, u["role"].value, u["designation"],
                    u["organization"], u["department"], u["avatar_color"],
                    now_str
                ))


def get_demo_users() -> List[DemoUserCredential]:
    """Returns list of pre-configured demo user accounts for one-click instant testing."""
    return [
        DemoUserCredential(
            user_id=u["user_id"],
            username=u["username"],
            email=u["email"],
            default_password=u["raw_password"],
            role=u["role"],
            role_title=u["role"].value.replace("_", " "),
            full_name=u["full_name"],
            designation=u["designation"],
            organization=u["organization"],
            badge_theme=u["badge_theme"],
            description=u["description"],
            key_features=u["key_features"]
        )
        for u in PRE_SEEDED_USERS
    ]


def authenticate_user(username_or_email: str, password: str, ip_address: str = "127.0.0.1", user_agent: str = "Unknown") -> Optional[LoginResponse]:
    """Authenticates credentials, logs audit event, and returns access token + profile."""
    init_auth_tables()
    conn = get_db_connection()
    target = username_or_email.strip().lower()
    
    row = conn.execute("""
        SELECT * FROM users 
        WHERE (LOWER(username) = ? OR LOWER(email) = ?) AND is_active = 1
    """, (target, target)).fetchone()

    if not row:
        return None

    is_valid = verify_password(password, row["password_hash"], row["password_salt"])
    if not is_valid:
        return None

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_str = now_dt.isoformat()

    # Update last login
    with conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE user_id = ?", (now_str, row["user_id"]))

    role_enum = UserRole(row["role"])
    permissions = get_permissions_for_role(role_enum)

    user_obj = User(
        user_id=row["user_id"],
        username=row["username"],
        email=row["email"],
        full_name=row["full_name"],
        role=role_enum,
        designation=row["designation"],
        organization=row["organization"],
        department=row["department"],
        avatar_color=row["avatar_color"],
        permissions=permissions,
        is_active=bool(row["is_active"]),
        last_login_at=now_str,
        created_at=row["created_at"]
    )

    token = create_access_token(
        user_id=user_obj.user_id,
        username=user_obj.username,
        email=user_obj.email,
        role=user_obj.role
    )

    # Log login audit
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with conn:
        conn.execute("""
            INSERT INTO audit_events (
                event_id, timestamp, event_type, entity_type, entity_id, action, actor, sha256_hash, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"AUTH-{int(datetime.datetime.now().timestamp()*1000)}",
            now_str,
            "USER_LOGIN",
            "USER_SESSION",
            user_obj.user_id,
            "LOGIN_SUCCESS",
            user_obj.username,
            token_hash,
            json.dumps({"ip": ip_address, "role": user_obj.role.value, "ua": user_agent})
        ))

    # Determine description and accessible features
    role_meta = next((u for u in PRE_SEEDED_USERS if u["role"] == role_enum), None)
    desc = role_meta["description"] if role_meta else f"Authorized {user_obj.role.value} Session"
    features = role_meta["key_features"] if role_meta else permissions

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400 * 7,
        user=user_obj,
        role_description=desc,
        accessible_features=features
    )


def get_user_by_id(user_id: str) -> Optional[User]:
    """Fetches user profile by user_id."""
    init_auth_tables()
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE user_id = ? AND is_active = 1", (user_id,)).fetchone()
    if not row:
        return None
    role_enum = UserRole(row["role"])
    return User(
        user_id=row["user_id"],
        username=row["username"],
        email=row["email"],
        full_name=row["full_name"],
        role=role_enum,
        designation=row["designation"],
        organization=row["organization"],
        department=row["department"],
        avatar_color=row["avatar_color"],
        permissions=get_permissions_for_role(role_enum),
        is_active=bool(row["is_active"]),
        last_login_at=row["last_login_at"],
        created_at=row["created_at"]
    )


def switch_user_role(current_user: User, target_role: UserRole) -> LoginResponse:
    """Instantly switches active persona/role for fast executive demonstration."""
    conn = get_db_connection()
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Check if target role matches a pre-seeded account
    target_seed = next((u for u in PRE_SEEDED_USERS if u["role"] == target_role), None)
    if target_seed:
        user_row = conn.execute("SELECT * FROM users WHERE user_id = ?", (target_seed["user_id"],)).fetchone()
        if user_row:
            switched_user = get_user_by_id(target_seed["user_id"])
        else:
            switched_user = current_user
            switched_user.role = target_role
            switched_user.permissions = get_permissions_for_role(target_role)
    else:
        switched_user = current_user
        switched_user.role = target_role
        switched_user.permissions = get_permissions_for_role(target_role)

    token = create_access_token(
        user_id=switched_user.user_id,
        username=switched_user.username,
        email=switched_user.email,
        role=switched_user.role
    )

    role_meta = next((u for u in PRE_SEEDED_USERS if u["role"] == target_role), None)
    desc = role_meta["description"] if role_meta else f"Active {target_role.value} Session"
    features = role_meta["key_features"] if role_meta else switched_user.permissions

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400 * 7,
        user=switched_user,
        role_description=desc,
        accessible_features=features
    )


# FastAPI Dependency Helpers
def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
) -> Optional[User]:
    """Extracts user from Authorization header if provided, otherwise returns None without error."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif authorization and not authorization.startswith("Bearer "):
        token = authorization.strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token:
        return None

    payload = verify_access_token(token)
    if not payload:
        return None

    user = get_user_by_id(payload.get("uid", ""))
    return user


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
) -> User:
    """Enforces authentication; raises HTTP 401 if token is missing or invalid."""
    user = get_current_user_optional(authorization, x_api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token in the Authorization header.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_permission(permission_name: str):
    """Dependency factory checking if current user possesses specific permission."""
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not check_has_permission(user.role, permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: Role '{user.role.value}' does not possess required permission '{permission_name}'."
            )
        return user
    return dependency


def get_default_guest_user() -> User:
    """Returns guest auditor fallback user for public/unauthenticated exploration."""
    return User(
        user_id="USR-GUEST-DEFAULT",
        username="guest_auditor",
        email="auditor@sih2026.gov.in",
        full_name="Public Statistical Reviewer",
        role=UserRole.PUBLIC_AUDITOR,
        designation="Public Auditor & Explorer",
        organization="Independent Public Observation",
        department="General Transparency",
        avatar_color="#94a3b8",
        permissions=get_permissions_for_role(UserRole.PUBLIC_AUDITOR),
        is_active=True,
        last_login_at=None,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
