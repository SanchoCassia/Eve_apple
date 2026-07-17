#!/usr/bin/env python3
"""
build.py — 从 content/ 里的 Markdown 文件生成独立页面
用法：python build.py
生成：index.html + books.html + films.html + tv.html + photos.html
"""

import os, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONTENT = BASE / 'content'
TEMPLATES = BASE / 'templates'

# 分类配置
CATEGORIES = {
    'books': {'icon': '📖', 'title': '书', 'file': 'books.html'},
    'films': {'icon': '🎬', 'title': '电影', 'file': 'films.html'},
    'tv':    {'icon': '📺', 'title': '电视', 'file': 'tv.html'},
    'photos':{'icon': '📷', 'title': '照片', 'file': 'photos.html'},
}

# 依赖
try:
    import yaml
except ImportError:
    yaml = None


def parse_frontmatter(text):
    """解析 YAML frontmatter"""
    text = text.strip()
    meta = {}
    body = text
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            if yaml:
                meta = yaml.safe_load(fm_text) or {}
            else:
                for line in fm_text.split('\n'):
                    if ':' in line:
                        k, v = line.split(':', 1)
                        k = k.strip()
                        v = v.strip().strip('"\'')
                        if k in ('tags',):
                            if v.startswith('[') and v.endswith(']'):
                                meta[k] = [t.strip().strip('"\'') for t in v[1:-1].split(',') if t.strip()]
                            else:
                                meta[k] = [v]
                        elif k == 'rating':
                            try: meta[k] = int(v)
                            except: meta[k] = 0
                        else:
                            meta[k] = v
    return meta, body


def esc(s):
    """HTML 转义"""
    if not isinstance(s, str):
        s = str(s)
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))


def stars_html(n):
    n = int(n)
    filled = '★' * n
    empty  = '☆' * (5 - n)
    return f'<span class="card-rating">{filled}{empty}</span>'


def truncate(text, n=120):
    text = re.sub(r'<[^>]+>', '', text).strip()
    return text[:n].rstrip() + '…' if len(text) > n else text


def collect_cards(category):
    """扫描 content/{category}/ → 卡片 HTML 列表"""
    cards = []
    cat_dir = CONTENT / category
    if not cat_dir.exists():
        return cards
    for f in sorted(cat_dir.iterdir(), reverse=True):
        if f.suffix.lower() not in ('.md', '.markdown'):
            continue
        meta, body = parse_frontmatter(f.read_text('utf-8'))
        title = meta.get('title', f.stem)
        author = meta.get('author', meta.get('director', ''))
        date = meta.get('date', '')
        rating = meta.get('rating', 0)
        tags = meta.get('tags', [])
        desc = esc(body)

        t = '<div class="card">'
        t += f'<div class="card-title">{esc(title)}</div>'
        t += f'<div class="card-meta">{esc(author)}{" · " + str(date) if author and date else (str(date) if date else "")}</div>'
        if desc:
            t += f'<div class="card-desc">{esc(desc)}</div>'
        if rating:
            t += stars_html(rating)
        if tags:
            t += '<div class="card-tags">' + ''.join(f'<span class="tag">{esc(str(t))}</span>' for t in tags) + '</div>'
        t += '</div>'
        cards.append(t)
    return cards


def collect_books_grouped():
    """扫描 content/books/ → 按 status 分组返回 HTML"""
    groups = {'read': [], 'want': []}
    cat_dir = CONTENT / 'books'
    if not cat_dir.exists():
        return '', 0

    for f in sorted(cat_dir.iterdir(), reverse=True):
        if f.suffix.lower() not in ('.md', '.markdown'):
            continue
        meta, body = parse_frontmatter(f.read_text('utf-8'))
        status = meta.get('status', 'read')
        title = meta.get('title', f.stem)
        author = meta.get('author', '')
        date = meta.get('date', '')
        rating = meta.get('rating', 0)
        tags = meta.get('tags', [])
        desc = esc(body)

        card = '<div class="card">'
        card += f'<div class="card-title">{esc(title)}</div>'
        card += f'<div class="card-meta">{esc(author)}{" · " + str(date) if author and date else (str(date) if date else "")}</div>'
        if desc:
            card += f'<div class="card-desc">{esc(desc)}</div>'
        if rating:
            card += stars_html(rating)
        if tags:
            card += '<div class="card-tags">' + ''.join(f'<span class="tag">{esc(str(t))}</span>' for t in tags) + '</div>'
        excerpts = meta.get('excerpts', [])
        if excerpts:
            card += '<div class="card-excerpts">'
            for ex in excerpts[:2]:
                card += '<div class="card-excerpt">\u201c' + esc(ex) + '\u201d</div>'
            if len(excerpts) > 2:
                card += '<div class="card-excerpt-more">\u2026还有 ' + str(len(excerpts)-2) + ' 条摘抄</div>'
            card += '</div>'
        card += '</div>'

        if status == 'want':
            groups['want'].append(card)
        else:
            groups['read'].append(card)

    # 生成带二级标题的 HTML
    parts = []
    total = 0
    for key, label in [('read', '看过的书'), ('want', '想看的书')]:
        items = groups[key]
        if items:
            parts.append(f'<h2 class="section-subtitle">{label} <span class="badge">{len(items)}</span></h2>')
            parts.append('<div class="card-grid">\n' + '\n'.join(items) + '\n</div>')
            total += len(items)

    html = '\n'.join(parts)
    if not html:
        html = '<div class="empty-state">还没有记录。</div>'
    return html, total


def collect_photos():
    """扫描 content/photos/ → 照片网格 HTML"""
    cells = []
    cat_dir = CONTENT / 'photos'
    if not cat_dir.exists():
        return cells
    for f in sorted(cat_dir.iterdir(), reverse=True):
        if f.suffix.lower() not in ('.md', '.markdown'):
            continue
        meta, body = parse_frontmatter(f.read_text('utf-8'))
        title = meta.get('title', f.stem)
        file = meta.get('file', '')

        desc = truncate(body, 60) if body else ''

        if file and (BASE / file).exists():
            cells.append(f'''<div class="photo-item">
              <img src="{esc(file)}" alt="{esc(title)}">
              <div class="photo-label">{esc(title)}</div>
            </div>''')
        else:
            cells.append(f'<div class="photo-empty">{esc(title)}</div>')
    return cells


def generate_category_page(category_key, cards, prebuilt_html=None, prebuilt_count=0):
    """从模板生成分类页面"""
    if prebuilt_html is not None:
        cards_html = prebuilt_html
        count_text = f'共 {prebuilt_count} 条'
    elif not cards:
        cards_html = '<div class="empty-state">还没有记录。</div>'
        count_text = '0 条'
    else:
        count_text = f'共 {len(cards)} 条'
        if category_key == 'photos':
            cards_html = '<div class="photo-grid">\n' + '\n'.join(cards) + '\n</div>'
        else:
            cards_html = '<div class="card-grid">\n' + '\n'.join(cards) + '\n</div>'
    cat = CATEGORIES[category_key]

    tmpl_path = TEMPLATES / 'category.html'
    if not tmpl_path.exists():
        print(f'⚠ 模板文件不存在: {tmpl_path}')
        return

    html = tmpl_path.read_text('utf-8')
    html = html.replace('__CATEGORY__', category_key)
    html = html.replace('__TITLE__', cat['title'])
    html = html.replace('__HEADER_ICON__', cat['icon'])
    html = html.replace('__HEADER_TITLE__', cat['title'])
    html = html.replace('__HEADER_COUNT__', count_text)
    html = html.replace('__CONTENT__', cards_html)

    output_path = BASE / cat['file']
    output_path.write_text(html, 'utf-8')
    return cat['file']


def generate_homepage():
    """更新首页的记录数（首页本身不动，只更新 footer）"""
    total = 0
    for cat_key in CATEGORIES:
        cat_dir = CONTENT / cat_key
        if cat_dir.exists():
            total += sum(1 for f in cat_dir.iterdir()
                         if f.suffix.lower() in ('.md', '.markdown'))
    return total


def generate_total_json(total):
    """生成总数 JSON 供首页 footer 调用"""
    import json
    (BASE / 'api').mkdir(exist_ok=True)
    (BASE / 'api' / 'total').write_text(
        json.dumps({'total': total}, ensure_ascii=False),
        'utf-8'
    )
    # 也做一份在根目录方便
    (BASE / 'total.json').write_text(
        json.dumps({'total': total}, ensure_ascii=False),
        'utf-8'
    )


def build():
    print('📦 构建个人网站...')
    total = 0

    for cat_key in CATEGORIES:
        if cat_key == 'books':
            html, count = collect_books_grouped()
            file_name = generate_category_page(cat_key, None, prebuilt_html=html, prebuilt_count=count)
        elif cat_key == 'photos':
            items = collect_photos()
            file_name = generate_category_page(cat_key, items)
            count = len(items)
        else:
            items = collect_cards(cat_key)
            file_name = generate_category_page(cat_key, items)
            count = len(items)
        total += count
        icon = CATEGORIES[cat_key]['icon']
        actual_count = count
        print(f'   {icon} {cat_key}: {actual_count} 条 → {file_name}')

    generate_total_json(total)
    print(f'   共 {total} 条记录')
    print('✅ 完成！')


if __name__ == '__main__':
    build()
