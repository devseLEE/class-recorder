# Streamlit 앱 (속도 최적화 적용)
import streamlit as st
import pandas as pd
from datetime import date
import firebase_admin
from firebase_admin import credentials, firestore, storage
import toml

# --- Firebase 초기화 (secrets.toml 기반) ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        firebase_key_dict = dict(st.secrets["FIREBASE_KEY"])
        cred = credentials.Certificate(firebase_key_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': f"{firebase_key_dict['project_id']}.appspot.com"
        })
    return firestore.client(), storage.bucket()

db, bucket = init_firebase()

# --- 캐시된 데이터 호출 함수 ---
@st.cache_data(ttl=60)
def get_subjects():
    return [doc.to_dict() | {"id": doc.id} for doc in db.collection("subjects").stream()]

@st.cache_data(ttl=60)
def get_classes():
    return [doc.to_dict() | {"id": doc.id} for doc in db.collection("classes").stream()]

@st.cache_data(ttl=60)
def get_students(class_id):
    return [doc.to_dict() for doc in db.collection("classes").document(class_id).collection("students").stream()]

@st.cache_data(ttl=60)
def get_schedule(class_id):
    return [doc.to_dict() for doc in db.collection("classes").document(class_id).collection("schedule").stream()]

@st.cache_data(ttl=60)
def get_attendance(class_id):
    return [doc.to_dict() for doc in db.collection("classes").document(class_id).collection("attendance").stream()]

# --- 메뉴 선택 ---
menu = st.sidebar.selectbox("메뉴 선택", [
    "교과 등록/조회", "수업 반 등록", "학생 등록",
    "진도 기록", "진도 조회", "출결 기록", "출결 조회"
])

# --- 교과 등록/조회 ---
if menu == "교과 등록/조회":
    st.header("📥 교과 등록")
    subject = st.selectbox("교과명", ["국어", "도덕", "사회", "수학", "과학", "체육", "실과", "음악", "미술", "영어"])
    year = st.selectbox("학년도", list(range(2015, 2026)))
    semester = st.selectbox("학기", [1, 2])
    file = st.file_uploader("수업 및 평가계획서 업로드 (PDF)", type="pdf")

    if st.button("교과 등록") and file:
        blob = bucket.blob(f"plans/{file.name}")
        blob.upload_from_file(file)
        blob.make_public()
        db.collection("subjects").add({
            "name": subject,
            "year": year,
            "semester": semester,
            "pdf_url": blob.public_url
        })
        st.success("교과가 등록되었습니다.")

    st.header("📖 교과 목록")
    for d in get_subjects():
        st.subheader(f"{d['year']}년 {d['semester']}학기 - {d['name']}")
        st.components.v1.iframe(d['pdf_url'], height=500)

# --- 수업 반 등록 ---
elif menu == "수업 반 등록":
    st.header("🏫 수업 반 등록")
    subjects = get_subjects()
    subject_list = [f"{d['year']}년 {d['semester']}학기 - {d['name']}" for d in subjects]
    selected_subject = st.selectbox("교과 선택", subject_list)
    class_name = st.text_input("수업 반 이름")
    weekdays = st.multiselect("수업 요일", ["월", "화", "수", "목", "금"])
    periods = st.multiselect("수업 교시", list(range(1, 8)))

    if st.button("반 등록"):
        db.collection("classes").add({
            "subject": selected_subject,
            "class": class_name,
            "weekdays": weekdays,
            "periods": periods
        })
        st.success("수업 반이 등록되었습니다.")

# --- 학생 등록 ---
elif menu == "학생 등록":
    st.header("👩‍🎓 학생 등록")
    classes = get_classes()
    class_dict = {c['id']: c['class'] for c in classes}
    selected_class_id = st.selectbox("수업 반 선택", list(class_dict.keys()), format_func=lambda x: class_dict[x])

    with st.form("학생 직접 입력"):
        sid = st.text_input("학번")
        name = st.text_input("이름")
        if st.form_submit_button("학생 추가"):
            db.collection("classes").document(selected_class_id).collection("students").add({"id": sid, "name": name})
            st.success("학생이 추가되었습니다.")

    csv_file = st.file_uploader("CSV 업로드 (id,name 형식)", type="csv")
    if csv_file:
        df = pd.read_csv(csv_file)
        for _, row in df.iterrows():
            db.collection("classes").document(selected_class_id).collection("students").add(row.to_dict())
        st.success("CSV 학생 등록 완료")

# --- 진도 기록 ---
elif menu == "진도 기록":
    st.header("📅 진도 기록")
    classes = get_classes()
    class_dict = {c['id']: c['class'] for c in classes}
    selected_class_id = st.selectbox("수업 반 선택", list(class_dict.keys()), format_func=lambda x: class_dict[x])
    record_date = st.date_input("날짜", value=date.today())
    period = st.selectbox("교시", list(range(1, 8)))
    content = st.text_area("진도 내용")
    note = st.text_area("특기사항")

    if st.button("기록 저장"):
        db.collection("classes").document(selected_class_id).collection("schedule").add({
            "date": str(record_date),
            "period": period,
            "content": content,
            "note": note
        })
        st.success("진도 기록이 저장되었습니다.")

# --- 진도 조회 ---
elif menu == "진도 조회":
    st.header("📋 진도 조회")
    start_date = st.date_input("시작일")
    end_date = st.date_input("종료일")
    rows = []
    for c in get_classes():
        for d in get_schedule(c['id']):
            d_date = date.fromisoformat(d['date'])
            if start_date <= d_date <= end_date:
                rows.append({"반": c['class'], "날짜": d['date'], "교시": d['period'], "진도": d['content'], "특기사항": d['note']})
    st.dataframe(pd.DataFrame(rows).sort_values(by=["날짜", "반"]))

# --- 출결 기록 ---
elif menu == "출결 기록":
    st.header("🧑‍🏫 출결 기록")
    classes = get_classes()
    class_dict = {c['id']: c['class'] for c in classes}
    selected_class_id = st.selectbox("수업 반 선택", list(class_dict.keys()), format_func=lambda x: class_dict[x])
    record_date = st.date_input("출결 날짜", value=date.today())
    students = get_students(selected_class_id)
    status_options = ["출석", "지각", "조퇴", "결석"]

    for s in students:
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown(f"**{s['id']} {s['name']}**")
        with col2:
            status = st.radio(f"출결 상태 ({s['name']})", status_options, key=f"status_{s['id']}", horizontal=True)
            note = st.text_input(f"특기사항 ({s['name']})", key=f"note_{s['id']}")
            if st.button(f"기록 저장 ({s['name']})"):
                db.collection("classes").document(selected_class_id).collection("attendance").add({
                    "student_id": s['id'], "name": s['name'], "date": str(record_date), "status": status, "note": note
                })
                st.success(f"{s['name']}의 출결이 저장되었습니다.")

# --- 출결 조회 ---
elif menu == "출결 조회":
    st.header("📊 출결 조회")
    start_date = st.date_input("조회 시작일")
    end_date = st.date_input("조회 종료일")
    rows = []
    for c in get_classes():
        for a in get_attendance(c['id']):
            a_date = date.fromisoformat(a['date'])
            if start_date <= a_date <= end_date:
                rows.append({
                    "반": c['class'], "날짜": a['date'], "학번": a['student_id'],
                    "이름": a['name'], "출결": a['status'], "특기사항": a['note']
                })
    st.dataframe(pd.DataFrame(rows).sort_values(by=["날짜", "반", "이름"]))
