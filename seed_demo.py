import argparse
import sys
from typing import Optional, Tuple

from config import firebase_config, firebase_admin_config  # ensures env is loaded/validated

import firebase_admin
from firebase_admin import credentials, auth as admin_auth, db


def initialize_firebase_if_needed() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_admin_config)
        firebase_admin.initialize_app(cred, {
            'databaseURL': firebase_config['databaseURL']
        })


def get_or_create_user(email: str, password: str, display_name: Optional[str] = None, force_reset_password: bool = False) -> Tuple[str, bool]:
    """Return (uid, created). Creates if missing. Optionally resets password if user exists.
    """
    try:
        user = admin_auth.get_user_by_email(email)
        uid = user.uid
        if force_reset_password:
            admin_auth.update_user(uid, password=password)
        # Update display name if provided and different
        if display_name and user.display_name != display_name:
            admin_auth.update_user(uid, display_name=display_name)
        return uid, False
    except admin_auth.UserNotFoundError:
        user = admin_auth.create_user(email=email, password=password, display_name=display_name)
        return user.uid, True


def ensure_doctor_record(doctor_uid: str, email: str, invite_code: str) -> None:
    doctors_ref = db.reference('/doctors')
    # Ensure invite code uniqueness (best-effort)
    existing = doctors_ref.order_by_child('inviteCode').equal_to(invite_code).get()
    if existing and (doctor_uid not in existing):
        # If another record already owns this code, keep it but still create/update the doctor entry with email only
        doctors_ref.child(doctor_uid).update({'email': email})
        return
    doctors_ref.child(doctor_uid).update({'email': email, 'inviteCode': invite_code})


def ensure_patient_record(patient_uid: str, email: str, invite_code: str, linked_doctor_uid: Optional[str]) -> None:
    users_ref = db.reference('/users')
    data = users_ref.child(patient_uid).get() or {}
    # Minimal record + linkage via invite/doctor uid if provided
    base = {
        'email': email,
        'invite_code': invite_code,
    }
    if linked_doctor_uid:
        base['linkedDoctorUID'] = linked_doctor_uid
    base.update(data)  # do not erase existing fields if present
    users_ref.child(patient_uid).set(base)


def backfill_linkage_via_invite(patient_uid: str, invite_code: str) -> Optional[str]:
    doctors_ref = db.reference('/doctors').order_by_child('inviteCode').equal_to(invite_code).get()
    if not doctors_ref:
        return None
    doctor_uid = list(doctors_ref.keys())[0]
    db.reference('/users').child(patient_uid).update({'linkedDoctorUID': doctor_uid})
    return doctor_uid


def seed_sample_chat(patient_uid: str) -> None:
    chat = [
        {"user": "Hi, I have been feeling mild headaches since yesterday.", "ai": "Thanks for sharing. On a scale of 1-10, how intense are they?"},
        {"user": "Maybe a 4. I also didn't sleep well.", "ai": "That can contribute. Stay hydrated and rest today. If it worsens to 7+, consider seeing a doctor."},
    ]
    db.reference('/chats').child(patient_uid).set(chat)


def seed_direct_message(patient_uid: str, doctor_uid: str) -> None:
    msg_ref = db.reference('/direct_messages').child(patient_uid)
    msg_ref.push({
        'from': doctor_uid,
        'message': 'Please monitor your symptoms and update me tomorrow.',
        'timestamp': {'.sv': 'timestamp'}
    })


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description='Seed demo doctor/patient accounts and data.')
    parser.add_argument('--doctor-email', required=True)
    parser.add_argument('--doctor-password', required=True)
    parser.add_argument('--invite-code', required=True)
    parser.add_argument('--patient-email', required=True)
    parser.add_argument('--patient-password', required=True)
    parser.add_argument('--reset-passwords', action='store_true', help='Force reset passwords if users already exist')
    parser.add_argument('--seed-chat', action='store_true', help='Seed a small sample chat and a direct message')
    args = parser.parse_args(argv)

    initialize_firebase_if_needed()

    # Create/ensure doctor
    doctor_uid, doctor_created = get_or_create_user(
        email=args.doctor_email,
        password=args.doctor_password,
        display_name='Dr. Demo',
        force_reset_password=args.reset_passwords
    )
    ensure_doctor_record(doctor_uid, args.doctor_email, args.invite_code)

    # Create/ensure patient
    patient_uid, patient_created = get_or_create_user(
        email=args.patient_email,
        password=args.patient_password,
        display_name='Patient Demo',
        force_reset_password=args.reset_passwords
    )

    ensure_patient_record(patient_uid, args.patient_email, args.invite_code, linked_doctor_uid=doctor_uid)

    if args.seed_chat:
        seed_sample_chat(patient_uid)
        seed_direct_message(patient_uid, doctor_uid)

    print('\nSeeding complete:')
    print(f'  Doctor:  {args.doctor_email} (uid={doctor_uid}, created={doctor_created})')
    print(f'  Patient: {args.patient_email} (uid={patient_uid}, created={patient_created})')
    print(f'  Invite code: {args.invite_code}')
    if args.seed_chat:
        print('  Sample chat and one direct message were created.')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())


