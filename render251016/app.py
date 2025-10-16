
from __future__ import annotations
from flask import Flask, render_template, request, redirect, url_for, abort, jsonify
from sqlalchemy import create_engine, Integer, String, Text, DateTime, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from contextlib import contextmanager
import os

# ------------------------
# Flask app
# ------------------------
app = Flask(__name__)

# ------------------------
# SQLAlchemy setup (SQLite by default)
# ------------------------
DB_URL = os.environ.get("BLOG_DB_URL", "sqlite:///blog.db")
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

class Base(DeclarativeBase):
    pass

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

Base.metadata.create_all(engine)

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# Seed a couple of posts on first run (if table empty)
with get_session() as s:
    if s.scalar(select(func.count(Post.id))) == 0:
        s.add_all([
            Post(title="Hello SQLAlchemy", author="Alice",
                 content="This is your first DB-backed post.\nIt persists in SQLite."),
            Post(title="Edit & Delete", author="Bob",
                 content="You can edit or delete this post from the UI below.")
        ])

# ------------------------
# RESTful API (JSON) — CRUD
# Base URL: /api/posts
# ------------------------

def post_to_dict(p: Post):
    return {
        "id": p.id, "title": p.title, "author": p.author,
        "content": p.content, "created_at": p.created_at.isoformat() if p.created_at else None
    }

@app.get("/api/posts")
def api_list_posts():
    with get_session() as s:
        posts = s.scalars(select(Post).order_by(Post.id.desc())).all()
        return jsonify([post_to_dict(p) for p in posts])

@app.get("/api/posts/<int:post_id>")
def api_get_post(post_id: int):
    with get_session() as s:
        p = s.get(Post, post_id)
        if not p:
            return jsonify({"error": "Not found"}), 404
        return jsonify(post_to_dict(p))

@app.post("/api/posts")
def api_create_post():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    author = (data.get("author") or "").strip()
    content = (data.get("content") or "").strip()
    if not title or not author or not content:
        return jsonify({"error": "title, author, content are required"}), 400
    with get_session() as s:
        p = Post(title=title, author=author, content=content)
        s.add(p)
        s.flush()  # populate id
        return jsonify(post_to_dict(p)), 201

@app.put("/api/posts/<int:post_id>")
def api_update_post(post_id: int):
    data = request.get_json(silent=True) or {}
    with get_session() as s:
        p = s.get(Post, post_id)
        if not p:
            return jsonify({"error": "Not found"}), 404
        # Partial update allowed
        if "title" in data:
            if not str(data["title"]).strip():
                return jsonify({"error": "title cannot be empty"}), 400
            p.title = str(data["title"]).strip()
        if "author" in data:
            if not str(data["author"]).strip():
                return jsonify({"error": "author cannot be empty"}), 400
            p.author = str(data["author"]).strip()
        if "content" in data:
            if not str(data["content"]).strip():
                return jsonify({"error": "content cannot be empty"}), 400
            p.content = str(data["content"]).strip()
        return jsonify(post_to_dict(p))

@app.delete("/api/posts/<int:post_id>")
def api_delete_post(post_id: int):
    with get_session() as s:
        p = s.get(Post, post_id)
        if not p:
            return jsonify({"error": "Not found"}), 404
        s.delete(p)
        return jsonify({"status": "deleted", "id": post_id})

# ------------------------
# HTML pages (templates)
# ------------------------

@app.get("/")
def index():
    with get_session() as s:
        posts = s.scalars(select(Post).order_by(Post.id.desc())).all()
        return render_template("index.html", posts=posts)

@app.get("/posts/new")
def new_post_page():
    return render_template("new_post.html")

@app.post("/posts/new")
def new_post_action():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not author or not content:
        return render_template("new_post.html", error="All fields are required.",
                               title=title, author=author, content=content)
    with get_session() as s:
        p = Post(title=title, author=author, content=content)
        s.add(p)
        s.flush()
        return redirect(url_for("post_detail_page", post_id=p.id))

@app.get("/posts/<int:post_id>")
def post_detail_page(post_id: int):
    with get_session() as s:
        p = s.get(Post, post_id)
        if not p:
            abort(404)
        return render_template("post_detail.html", post=p)

@app.get("/posts/<int:post_id>/edit")
def edit_post_page(post_id: int):
    with get_session() as s:
        p = s.get(Post, post_id)
        if not p:
            abort(404)
        return render_template("edit_post.html", post=p)

@app.post("/posts/<int:post_id>/edit")
def edit_post_action(post_id: int):
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not author or not content:
        return render_template("edit_post.html", error="All fields are required.",
                               post={"id": post_id, "title": title, "author": author, "content": content})
    with get_session() as s:
        p = s.get(Post, post_id)
        if not p:
            abort(404)
        p.title, p.author, p.content = title, author, content
        return redirect(url_for("post_detail_page", post_id=post_id))

# Optional fallback HTML delete (if JS disabled): POST /posts/<id>/delete
@app.post("/posts/<int:post_id>/delete")
def delete_post_action(post_id: int):
    with get_session() as s:
        p = s.get(Post, post_id)
        if p:
            s.delete(p)
    return redirect(url_for("index"))

if __name__ == "__main__":
    # Run the dev server: python app.py
    # Open http://127.0.0.1:5000
    app.run(debug=True)
