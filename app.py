# streamlit_app_full.py
# 📌 통합 Streamlit 앱: 교과 등록 ~ 출결 조회까지 전 기능 구현

from firebase_admin import credentials, firestore, storage, initialize_app
import firebase_admin
import datetime
import pandas as pd
from datetime import date
import os
import json
import streamlit as st

# --- Firebase 초기화 (Streamlit secrets에서 키 불러오기) ---
if not firebase_admin._apps:
    # Streamlit Cloud 환경에서는 secrets.toml에서 키를 불러옵니다
    firebase_key_dict = st.secrets["general"]["firebase_key"]
    cred = credentials.Certificate(firebase_key_dict)
    initialize_app(cred, {
        'storageBucket': 'class-recoder.appspot.com'  # 버킷 이름 정확히 확인
    })

# --- Firebase 서비스 객체 생성 ---
db = firestore.client()
bucket = storage.bucket()

# --- 전체 메뉴 구성 ---
menu = st.sidebar.selectbox("메뉴 선택", [
    "교과 등록/조회", "수업 반 등록", "학생 등록",
    "진도 기록", "진도 조회", "출결 기록", "출결 조회"
])

# --- 1. 교과 등록/조회 ---
if menu == "교과 등록/조회":
    st.header("📥 교과 등록")
    subject = st.selectbox("교과명", ["국어", "도덕", "사회", "수학", "과학", "체육", "실과", "음악", "미술", "영어"])
    year = st.selectbox("학년도", list(range(2015, 2025)))
    semester = st.selectbox("학기", [1, 2])
    file = st.file_uploader("수업 및 평가계획서 업로드 (PDF, 10MB 이하)", type="pdf")

    if st.button("교과 등록") and file:
        blob = bucket.blob(f"plans/{file.name}")
        blob.upload_from_file(file)
        blob.make_public()
        doc = {
            "name": subject,
            "year": year,
            "semester": semester,
            "pdf_url": blob.public_url
        }
        db.collection("subjects").add(doc)
        st.success("교과 등록 완료")

    st.header("📖 교과 목록")
    subjects = db.collection("subjects").stream()
    for sub in subjects:
        data = sub.to_dict()
        st.subheader(f"{data['year']}년 {data['semester']}학기 - {data['name']}")
        st.components.v1.iframe(data['pdf_url'], height=500)

# --- 2. 수업 반 등록 ---
elif menu == "수업 반 등록":
    st.header("🏫 수업 반 등록")
    subject_ref = db.collection("subjects").stream()
    subject_list = [f"{s.to_dict()['year']}년 {s.to_dict()['semester']}학기 - {s.to_dict()['name']}" for s in subject_ref]
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

# --- 3. 학생 등록 ---
elif menu == "학생 등록":
    st.header("👩‍🎓 학생 등록")
    class_list = db.collection("classes").stream()
    class_ids = {c.id: c.to_dict()['class'] for c in class_list}
    selected_id = st.selectbox("수업 반 선택", list(class_ids.keys()), format_func=lambda x: class_ids[x])

    with st.form("add_student"):
        col1, col2 = st.columns(2)
        with col1:
            sid = st.text_input("학번 (예: 250101)")
        with col2:
            name = st.text_input("이름")
        submit = st.form_submit_button("학생 추가")

    if submit:
        db.collection("classes").document(selected_id).collection("students").add({"id": sid, "name": name})
        st.success("학생이 추가되었습니다.")

    csv_file = st.file_uploader("CSV 업로드 (id,name 형식)", type="csv")
    if csv_file:
        df = pd.read_csv(csv_file)
        for _, row in df.iterrows():
            db.collection("classes").document(selected_id).collection("students").add(row.to_dict())
        st.success("CSV 학생 등록 완료")

# --- 4. 진도 기록 ---
elif menu == "진도 기록":
    st.header("📅 진도 기록")
    class_list = db.collection("classes").stream()
    class_ids = {c.id: c.to_dict()['class'] for c in class_list}
    selected_id = st.selectbox("수업 반 선택", list(class_ids.keys()), format_func=lambda x: class_ids[x])
    record_date = st.date_input("날짜 선택", value=date.today())
    period = st.selectbox("교시", list(range(1, 8)))
    content = st.text_area("진도 내용")
    note = st.text_area("특기사항")
    if st.button("기록 저장"):
        db.collection("classes").document(selected_id).collection("schedule").add({
            "date": str(record_date),
            "period": period,
            "content": content,
            "note": note
        })
        st.success("진도 기록이 저장되었습니다.")

# --- 5. 진도 조회 ---
elif menu == "진도 조회":
    st.header("📋 진도 조회")
    start_date = st.date_input("시작일")
    end_date = st.date_input("종료일")
    all_classes = db.collection("classes").stream()
    result_rows = []
    for c in all_classes:
        cname = c.to_dict()['class']
        schedule_ref = db.collection("classes").document(c.id).collection("schedule").stream()
        for sch in schedule_ref:
            d = sch.to_dict()
            d_date = date.fromisoformat(d['date'])
            if start_date <= d_date <= end_date:
                result_rows.append({
                    "반": cname,
                    "날짜": d['date'],
                    "교시": d['period'],
                    "진도": d['content'],
                    "특기사항": d['note']
                })
    df = pd.DataFrame(result_rows)
    st.dataframe(df.sort_values(by=["날짜", "반"]))

# --- 6. 출결 기록 ---
elif menu == "출결 기록":
    st.header("🧑‍🏫 출결 기록")
    class_list = db.collection("classes").stream()
    class_ids = {c.id: c.to_dict()['class'] for c in class_list}
    selected_id = st.selectbox("수업 반 선택", list(class_ids.keys()), format_func=lambda x: class_ids[x])
    record_date = st.date_input("출결 날짜", value=date.today())
    students = db.collection("classes").document(selected_id).collection("students").stream()
    status_options = ["출석", "지각", "조퇴", "결석"]
    st.write("학생별 출결 상태 선택")
    for s in students:
        sdata = s.to_dict()
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown(f"**{sdata['id']} {sdata['name']}**")
        with col2:
            selected_status = st.radio(
                f"출결 상태 ({sdata['name']})", status_options,
                key=f"status_{s.id}", horizontal=True
            )
            note = st.text_input(f"특기사항 ({sdata['name']})", key=f"note_{s.id}")
            if st.button(f"기록 저장 ({sdata['name']})"):
                db.collection("classes").document(selected_id).collection("attendance").add({
                    "student_id": sdata['id'],
                    "name": sdata['name'],
                    "date": str(record_date),
                    "status": selected_status,
                    "note": note
                })
                st.success(f"{sdata['name']}의 출결 기록이 저장되었습니다.")

# --- 7. 출결 조회 ---
elif menu == "출결 조회":
    st.header("📊 출결 조회")
    start_date = st.date_input("조회 시작일")
    end_date = st.date_input("조회 종료일")
    all_classes = db.collection("classes").stream()
    result_rows = []
    for c in all_classes:
        cname = c.to_dict()['class']
        att_ref = db.collection("classes").document(c.id).collection("attendance").stream()
        for att in att_ref:
            a = att.to_dict()
            a_date = date.fromisoformat(a['date'])
            if start_date <= a_date <= end_date:
                result_rows.append({
                    "반": cname,
                    "날짜": a['date'],
                    "학번": a['student_id'],
                    "이름": a['name'],
                    "출결": a['status'],
                    "특기사항": a['note']
                })
    df = pd.DataFrame(result_rows)
    st.dataframe(df.sort_values(by=["날짜", "반", "이름"]))
