import pandas as pd
import streamlit as st

import neo4j_service as db

st.set_page_config(page_title="GraphBook", page_icon="📚", layout="wide")
st.title("📚 GraphBook Recommendation System")

try:
    st.secrets["neo4j"]
except Exception:
    st.error("ยังไม่ได้ตั้งค่า Neo4j Secrets กรุณาสร้างไฟล์ .streamlit/secrets.toml ตามตัวอย่างใน README")
    st.stop()

if not db.check_connection():
    st.error("เชื่อมต่อ Neo4j ไม่สำเร็จ ตรวจสอบ uri, username, password และสถานะ Aura instance")
    st.stop()

page = st.sidebar.radio(
    "เมนู",
    ["Dashboard", "Recommendations", "Book Search", "Borrow / Rate", "Graph Explorer", "Admin / Setup"],
)


def student_picker(key: str):
    students = db.get_students()
    if not students:
        st.info("ยังไม่มีข้อมูลนักศึกษา ไปที่เมนู Admin / Setup เพื่อสร้างข้อมูลตัวอย่าง")
        st.stop()
    labels = {f'{s["name"]} ({s["id"]})': s["id"] for s in students}
    choice = st.selectbox("เลือกนักศึกษา", list(labels), key=key)
    return labels[choice]


if page == "Dashboard":
    s = db.get_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ผู้ใช้", s["students"])
    c2.metric("หนังสือ", s["books"])
    c3.metric("ประวัติการยืม", s["borrows"])
    c4.metric("ความสัมพันธ์เพื่อน", s["friendships"])
    st.subheader("หนังสือที่ถูกยืมมากที่สุด")
    top = db.top_borrowed()
    if top:
        st.dataframe(pd.DataFrame(top), use_container_width=True, hide_index=True)
    else:
        st.info("ยังไม่มีประวัติการยืม")

elif page == "Recommendations":
    sid = student_picker("rec_student")
    limit = st.slider("จำนวนหนังสือที่แนะนำ", 3, 15, 5)
    recs = db.recommend(sid, limit)
    if not recs:
        st.info("ยังไม่มีหนังสือที่แนะนำ ลองเพิ่มเพื่อนหรือความสนใจให้นักศึกษาคนนี้")
    for r in recs:
        with st.container(border=True):
            st.markdown(f'**{r["title"]}** — {r["author"]}')
            st.caption(f'คะแนน {r["score"]}')
            reasons = []
            if r["friend_count"]:
                reasons.append(f'เพื่อนที่ยืม {r["friend_count"]} คน ({", ".join(r["friends"])})')
            if r["interest_matches"]:
                reasons.append(f'ตรงความสนใจ: {", ".join(r["matched"])}')
            reasons.append(f'ถูกยืม {r["popularity"]} ครั้ง คะแนนเฉลี่ย {r["average_rating"]}')
            st.write("เหตุผล: " + " | ".join(reasons))
    with st.expander("สูตรคะแนน"):
        st.code("score = friend_count*3 + interest_matches*2 + popularity*0.20 + average_rating*0.50")
        st.caption("เป็นสูตรถ่วงน้ำหนักเพื่อการเรียนรู้ ไม่ใช่โมเดล Machine Learning")

elif page == "Book Search":
    kw = st.text_input("ค้นหาจากชื่อหนังสือ ผู้แต่ง หรือหมวดหมู่")
    if kw.strip():
        rows = db.search_books(kw.strip())
        if rows:
            df = pd.DataFrame(rows)
            df["author"] = df["author"].apply(", ".join)
            df["category"] = df["category"].apply(", ".join)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("ไม่พบหนังสือที่ตรงกับคำค้นหา")

elif page == "Borrow / Rate":
    sid = student_picker("borrow_student")
    books = db.get_books()
    labels = {b["title"]: b["id"] for b in books}
    title = st.selectbox("เลือกหนังสือ", list(labels))
    rating = st.slider("คะแนน", 1, 5, 4)
    if st.button("บันทึกการยืม"):
        db.borrow_book(sid, labels[title], rating)
        st.success("บันทึกการยืมแล้ว")
    st.subheader("ประวัติการยืม")
    hist = db.borrow_history(sid)
    if hist:
        st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)
    else:
        st.info("นักศึกษาคนนี้ยังไม่เคยยืมหนังสือ")

elif page == "Graph Explorer":
    sid = student_picker("graph_student")
    edges = db.student_graph(sid)
    if not edges:
        st.info("ยังไม่มีความสัมพันธ์ให้แสดง")
    else:
        colors = {"Student": "#9ecae1", "Book": "#fdd49e", "Category": "#c7e9c0"}
        dot = ["graph G { rankdir=LR; node [style=filled, shape=box, fontsize=11];"]
        root = edges[0]["a"]
        dot.append(f'"{root}" [fillcolor="#fc9272"];')
        for e in edges:
            b = e["b"].replace('"', "'")
            dot.append(f'"{b}" [fillcolor="{colors[e["b_type"]]}"];')
            dot.append(f'"{root}" -- "{b}" [label="{e["rel"]}", fontsize=9];')
        dot.append("}")
        st.graphviz_chart("\n".join(dot))
        st.caption("ฟ้า = เพื่อน | ส้มอ่อน = หนังสือที่ยืม | เขียว = หมวดที่สนใจ")

elif page == "Admin / Setup":
    st.write("สร้าง Constraint และข้อมูลตัวอย่างสำหรับทดลองระบบ (ใช้ MERGE จึงกดซ้ำได้)")
    if st.button("สร้าง Constraint + Demo Data"):
        db.setup_demo_data()
        st.success("สร้างข้อมูลตัวอย่างเรียบร้อย")
