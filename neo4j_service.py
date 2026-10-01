"""เชื่อมต่อ Neo4j Aura และรวมคำสั่ง Cypher ของระบบ GraphBook"""
import streamlit as st
from neo4j import GraphDatabase


@st.cache_resource
def get_driver():
    cfg = st.secrets["neo4j"]
    return GraphDatabase.driver(cfg["uri"], auth=(cfg["username"], cfg["password"]))


def run_query(query: str, params: dict | None = None) -> list[dict]:
    cfg = st.secrets["neo4j"]
    with get_driver().session(database=cfg.get("database", "neo4j")) as session:
        return [r.data() for r in session.run(query, params or {})]


def check_connection() -> bool:
    try:
        get_driver().verify_connectivity()
        return True
    except Exception:
        return False


# ---------- Dashboard ----------
def get_stats() -> dict:
    rows = run_query("""
        CALL { MATCH (s:Student) RETURN count(s) AS students }
        CALL { MATCH (b:Book) RETURN count(b) AS books }
        CALL { MATCH ()-[r:BORROWED]->() RETURN count(r) AS borrows }
        CALL { MATCH (:Student)-[r:FRIEND_OF]-(:Student) RETURN count(r) / 2 AS friendships }
        RETURN students, books, borrows, friendships
    """)
    return rows[0]


def get_students() -> list[dict]:
    return run_query("MATCH (s:Student) RETURN s.student_id AS id, s.name AS name ORDER BY s.name")


def get_books() -> list[dict]:
    return run_query("MATCH (b:Book) RETURN b.book_id AS id, b.title AS title ORDER BY b.title")


def top_borrowed(limit: int = 5) -> list[dict]:
    return run_query("""
        MATCH (:Student)-[r:BORROWED]->(b:Book)
        RETURN b.title AS title, count(r) AS borrows, round(avg(r.rating), 2) AS avg_rating
        ORDER BY borrows DESC, avg_rating DESC LIMIT $limit
    """, {"limit": limit})


# ---------- Recommendations ----------
RECOMMEND_QUERY = """
MATCH (me:Student {student_id: $sid})
MATCH (b:Book)
WHERE NOT (me)-[:BORROWED]->(b)
OPTIONAL MATCH (me)-[:FRIEND_OF]-(f:Student)-[:BORROWED]->(b)
WITH me, b, count(DISTINCT f) AS friend_count, collect(DISTINCT f.name) AS friends
OPTIONAL MATCH (b)-[:IN_CATEGORY]->(c:Category)<-[:INTERESTED_IN]-(me)
WITH me, b, friend_count, friends,
     count(DISTINCT c) AS interest_matches, collect(DISTINCT c.name) AS matched
OPTIONAL MATCH (:Student)-[r:BORROWED]->(b)
WITH b, friend_count, friends, interest_matches, matched,
     count(r) AS popularity, coalesce(avg(r.rating), 0.0) AS average_rating
WHERE friend_count > 0 OR interest_matches > 0
OPTIONAL MATCH (a:Author)-[:WROTE]->(b)
WITH b, friend_count, friends, interest_matches, matched, popularity, average_rating,
     coalesce(head(collect(a.name)), '-') AS author
RETURN b.title AS title, author,
       friend_count, interest_matches, popularity,
       round(average_rating, 2) AS average_rating,
       round(friend_count * 3 + interest_matches * 2
             + popularity * 0.20 + average_rating * 0.50, 2) AS score,
       friends, matched
ORDER BY score DESC, title
LIMIT $limit
"""


def recommend(student_id: str, limit: int = 10) -> list[dict]:
    return run_query(RECOMMEND_QUERY, {"sid": student_id, "limit": limit})


# ---------- Search ----------
def search_books(keyword: str) -> list[dict]:
    return run_query("""
        MATCH (b:Book)
        OPTIONAL MATCH (a:Author)-[:WROTE]->(b)
        OPTIONAL MATCH (b)-[:IN_CATEGORY]->(c:Category)
        WITH b, collect(DISTINCT a.name) AS authors, collect(DISTINCT c.name) AS cats
        WHERE toLower(b.title) CONTAINS toLower($kw)
           OR any(x IN authors WHERE toLower(x) CONTAINS toLower($kw))
           OR any(x IN cats WHERE toLower(x) CONTAINS toLower($kw))
        RETURN b.title AS title, authors AS author, cats AS category
        ORDER BY title
    """, {"kw": keyword})


# ---------- Borrow / Rate ----------
def borrow_book(student_id: str, book_id: str, rating: int) -> None:
    run_query("""
        MATCH (s:Student {student_id: $sid}), (b:Book {book_id: $bid})
        MERGE (s)-[r:BORROWED]->(b)
        SET r.borrow_date = toString(date()), r.rating = $rating
    """, {"sid": student_id, "bid": book_id, "rating": rating})


def borrow_history(student_id: str) -> list[dict]:
    return run_query("""
        MATCH (:Student {student_id: $sid})-[r:BORROWED]->(b:Book)
        RETURN b.title AS title, r.borrow_date AS borrow_date, r.rating AS rating
        ORDER BY borrow_date DESC
    """, {"sid": student_id})


# ---------- Graph Explorer ----------
def student_graph(student_id: str) -> list[dict]:
    """คืนเส้นความสัมพันธ์รอบตัวนักศึกษา: เพื่อน, หนังสือที่ยืม, ความสนใจ"""
    return run_query("""
        MATCH (me:Student {student_id: $sid})
        CALL {
          WITH me MATCH (me)-[:FRIEND_OF]-(x:Student)
          RETURN me.name AS a, 'FRIEND_OF' AS rel, x.name AS b, 'Student' AS b_type
          UNION
          WITH me MATCH (me)-[:BORROWED]->(x:Book)
          RETURN me.name AS a, 'BORROWED' AS rel, x.title AS b, 'Book' AS b_type
          UNION
          WITH me MATCH (me)-[:INTERESTED_IN]->(x:Category)
          RETURN me.name AS a, 'INTERESTED_IN' AS rel, x.name AS b, 'Category' AS b_type
        }
        RETURN a, rel, b, b_type
    """, {"sid": student_id})


# ---------- Admin / Setup ----------
CONSTRAINTS = [
    "CREATE CONSTRAINT student_id IF NOT EXISTS FOR (s:Student) REQUIRE s.student_id IS UNIQUE",
    "CREATE CONSTRAINT book_id IF NOT EXISTS FOR (b:Book) REQUIRE b.book_id IS UNIQUE",
    "CREATE CONSTRAINT author_name IF NOT EXISTS FOR (a:Author) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
]

STUDENTS = [
    {"id": "S001", "name": "Anan", "major": "Computer Science"},
    {"id": "S002", "name": "Beam", "major": "Computer Science"},
    {"id": "S003", "name": "Chai", "major": "Business"},
    {"id": "S004", "name": "Dao", "major": "Education"},
    {"id": "S005", "name": "Ekk", "major": "Engineering"},
    {"id": "S006", "name": "Fon", "major": "Business"},
]
BOOKS = [
    {"id": "B001", "title": "Python for Beginners", "author": "John Smith", "cat": "Programming"},
    {"id": "B002", "title": "Graph Databases", "author": "Ian Robinson", "cat": "Database"},
    {"id": "B003", "title": "Data Science Handbook", "author": "Jake Vander", "cat": "Data Science"},
    {"id": "B004", "title": "Clean Code", "author": "Robert Martin", "cat": "Programming"},
    {"id": "B005", "title": "The Lean Startup", "author": "Eric Ries", "cat": "Business"},
    {"id": "B006", "title": "Database System Concepts", "author": "Abraham Silberschatz", "cat": "Database"},
    {"id": "B007", "title": "Deep Learning Basics", "author": "Ian Goodfellow", "cat": "Data Science"},
    {"id": "B008", "title": "Good to Great", "author": "Jim Collins", "cat": "Business"},
]
FRIENDS = [("S001", "S002"), ("S001", "S003"), ("S002", "S004"),
           ("S003", "S006"), ("S004", "S005"), ("S005", "S001")]
INTERESTS = [("S001", "Programming"), ("S001", "Database"), ("S002", "Data Science"),
             ("S003", "Business"), ("S004", "Programming"), ("S005", "Database"),
             ("S006", "Business")]
BORROWS = [("S001", "B001", "2026-01-10", 5), ("S002", "B001", "2026-01-12", 4),
           ("S002", "B002", "2026-01-15", 5), ("S002", "B003", "2026-02-01", 4),
           ("S003", "B005", "2026-02-03", 5), ("S003", "B004", "2026-02-10", 3),
           ("S004", "B004", "2026-02-11", 4), ("S004", "B006", "2026-02-15", 4),
           ("S005", "B002", "2026-03-01", 5), ("S005", "B007", "2026-03-05", 3),
           ("S006", "B008", "2026-03-07", 4), ("S006", "B005", "2026-03-09", 5)]


def setup_demo_data() -> None:
    for c in CONSTRAINTS:
        run_query(c)
    run_query("""UNWIND $rows AS r MERGE (s:Student {student_id: r.id})
                 SET s.name = r.name, s.major = r.major""", {"rows": STUDENTS})
    run_query("""UNWIND $rows AS r
                 MERGE (b:Book {book_id: r.id}) SET b.title = r.title
                 MERGE (a:Author {name: r.author}) MERGE (a)-[:WROTE]->(b)
                 MERGE (c:Category {name: r.cat}) MERGE (b)-[:IN_CATEGORY]->(c)""", {"rows": BOOKS})
    run_query("""UNWIND $rows AS r
                 MATCH (a:Student {student_id: r[0]}), (b:Student {student_id: r[1]})
                 MERGE (a)-[:FRIEND_OF]-(b)""", {"rows": [list(x) for x in FRIENDS]})
    run_query("""UNWIND $rows AS r
                 MATCH (s:Student {student_id: r[0]}), (c:Category {name: r[1]})
                 MERGE (s)-[:INTERESTED_IN]->(c)""", {"rows": [list(x) for x in INTERESTS]})
    run_query("""UNWIND $rows AS r
                 MATCH (s:Student {student_id: r[0]}), (b:Book {book_id: r[1]})
                 MERGE (s)-[x:BORROWED]->(b)
                 SET x.borrow_date = r[2], x.rating = r[3]""", {"rows": [list(x) for x in BORROWS]})
