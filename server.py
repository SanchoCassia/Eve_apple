#!/usr/bin/env python3
"""
server.py — 本地管理服务器
用法：python server.py
访问 http://localhost:8080  看网站
访问 http://localhost:8080/admin  编辑内容
"""

import http.server
import json, os, subprocess, urllib.parse, base64, uuid, mimetypes
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONTENT = BASE / 'content'
UPLOADS = BASE / 'uploads' / 'photos'
PORT = 8080


# ── 工具函数 ──

def esc_md(s):
    """把用户输入里的 frontmatter 分隔符转义"""
    if not isinstance(s, str):
        s = str(s)
    return s.replace('---', '\\---')


def list_entries(category):
    """列出某分类下的所有 .md 文件"""
    cat_dir = CONTENT / category
    if not cat_dir.exists():
        return []
    entries = []
    for f in sorted(cat_dir.iterdir(), reverse=True):
        if f.suffix.lower() in ('.md', '.markdown'):
            meta, body = parse_frontmatter(f.read_text('utf-8'))
            entries.append({
                'slug': f.stem,
                'title': meta.get('title', f.stem),
                'date': meta.get('date', ''),
                'author': meta.get('author', meta.get('director', '')),
                'rating': meta.get('rating', 0),
                'status': meta.get('status', ''),
                'tags': meta.get('tags', []),
                'type': meta.get('type', ''),
                'file': meta.get('file', ''),
                'body': body[:100] + ('…' if len(body) > 100 else ''),
            })
    return entries


def get_entry(category, slug):
    """获取单篇文章"""
    f = CONTENT / category / f'{slug}.md'
    if not f.exists():
        return None
    meta, body = parse_frontmatter(f.read_text('utf-8'))
    return {
        'slug': slug,
        'title': meta.get('title', slug),
        'date': meta.get('date', ''),
        'author': meta.get('author', ''),
        'director': meta.get('director', ''),
        'rating': meta.get('rating', 0),
        'status': meta.get('status', 'read'),
        'tags': meta.get('tags', []),
        'type': meta.get('type', ''),
        'file': meta.get('file', ''),
        'body': body,
    }


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
            for line in fm_text.split('\n'):
                line = line.strip()
                if ':' in line:
                    k, v = line.split(':', 1)
                    k = k.strip()
                    v = v.strip().strip('"\'')
                    if k in ('tags',) and v:
                        # 简单支持 [tag1, tag2]
                        if v.startswith('[') and v.endswith(']'):
                            meta[k] = [t.strip().strip('"\'') for t in v[1:-1].split(',') if t.strip()]
                        else:
                            meta[k] = [v]
                    elif k == 'rating':
                        try:
                            meta[k] = int(v)
                        except ValueError:
                            meta[k] = 0
                    else:
                        meta[k] = v
    return meta, body


def build_frontmatter(data):
    """从 data dict 生成 frontmatter + body"""
    lines = ['---']
    for key in ['title', 'author', 'director', 'date', 'status', 'type', 'file']:
        val = data.get(key, '')
        if val:
            lines.append(f'{key}: {val}')
    rating = data.get('rating', 0)
    if rating:
        lines.append(f'rating: {int(rating)}')
    tags = data.get('tags', [])
    if tags and isinstance(tags, list):
        tag_str = ', '.join(f'"{t}"' for t in tags if t.strip())
        if tag_str:
            lines.append(f'tags: [{tag_str}]')
    elif tags and isinstance(tags, str) and tags.strip():
        lines.append(f'tags: [{tags}]')
    lines.append('---')
    lines.append('')
    lines.append(data.get('body', ''))
    return '\n'.join(lines)


def save_entry(category, slug, data):
    """保存文章到 .md 文件"""
    cat_dir = CONTENT / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    content = build_frontmatter(data)
    f = cat_dir / f'{slug}.md'
    f.write_text(content, 'utf-8')
    return True


def delete_entry(category, slug):
    """删除文章"""
    f = CONTENT / category / f'{slug}.md'
    if f.exists():
        f.unlink()
        return True
    return False


def run_build():
    """运行 build.py"""
    try:
        result = subprocess.run(
            ['python', str(BASE / 'build.py')],
            capture_output=True, text=True, cwd=BASE,
            timeout=30
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return '构建超时（30秒）'
    except Exception as e:
        return f'构建失败: {e}'


def git_push():
    """自动提交并推送到 GitHub"""
    try:
        # 添加所有变更
        r1 = subprocess.run(['git', 'add', '-A'], capture_output=True, text=True, cwd=BASE, timeout=10)
        # 提交（如果没有变更就不提交）
        r2 = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True, cwd=BASE, timeout=10)
        if r2.returncode == 0:
            return '没有新变更，跳过推送'
        r3 = subprocess.run(['git', 'commit', '-m', 'auto: 更新内容'], capture_output=True, text=True, cwd=BASE, timeout=10)
        # 推送到 GitHub
        r4 = subprocess.run(['git', 'push'], capture_output=True, text=True, cwd=BASE, timeout=60)
        if r4.returncode == 0:
            return '✅ 已推送到 GitHub'
        else:
            return f'⚠ 推送失败: {r4.stderr.strip()[:200]}'
    except subprocess.TimeoutExpired:
        return '⏱ 推送超时'
    except Exception as e:
        return f'⚠ 推送出错: {e}'


def handle_upload(data):
    """处理图片上传（base64 → 文件）"""
    filename = data.get('filename', 'photo.jpg')
    file_data = data.get('data', '')
    if not file_data:
        return {'error': 'no data'}

    # 从 base64 解码（支持 data:image/xxx;base64, 格式）
    if ',' in file_data:
        file_data = file_data.split(',', 1)[1]

    # 保留原扩展名
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
        ext = '.jpg'

    # 生成唯一文件名
    unique_name = f'{uuid.uuid4().hex}{ext}'
    UPLOADS.mkdir(parents=True, exist_ok=True)
    save_path = UPLOADS / unique_name

    try:
        raw = base64.b64decode(file_data)
        save_path.write_bytes(raw)
        rel_path = f'uploads/photos/{unique_name}'
        return {'url': rel_path, 'filename': unique_name}
    except Exception as e:
        return {'error': str(e)}


def json_response(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    return http.server.HTTPServer(('', 0), type('', (), {}))  # dummy, won't be used


class AdminHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP 请求处理"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # ── API 路由 ──
        if parsed.path == '/api/list':
            category = params.get('category', ['books'])[0]
            entries = list_entries(category)
            self._send_json(entries)

        elif parsed.path == '/api/get':
            category = params.get('category', ['books'])[0]
            slug = params.get('slug', [''])[0]
            if not slug:
                self._send_json({'error': 'missing slug'}, 400)
                return
            entry = get_entry(category, slug)
            if entry:
                self._send_json(entry)
            else:
                self._send_json({'error': 'not found'}, 404)

        elif parsed.path == '/admin':
            # 重定向到 admin.html
            self.send_response(302)
            self.send_header('Location', '/admin.html')
            self.end_headers()

        elif parsed.path == '/api/total':
            total = 0
            for cat in ('books', 'films', 'tv', 'photos'):
                cat_dir = CONTENT / cat
                if cat_dir.exists():
                    total += sum(1 for f in cat_dir.iterdir()
                                if f.suffix.lower() in ('.md', '.markdown'))
            self._send_json({'total': total})

        else:
            # 默认：静态文件
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode('utf-8')
        try:
            data = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            data = {}

        if not data and parsed.path not in ('/api/build', '/api/delete'):
            self._send_json({'error': 'invalid or empty body'}, 400)
            return

        if parsed.path == '/api/save':
            category = data.get('category', 'books')
            slug = data.get('slug', '')
            entry_data = data.get('data', {})
            if not slug:
                # 用 title 作为 slug
                slug = entry_data.get('title', 'untitled').strip()
                # 如果已存在则加数字后缀
                counter = 1
                orig_slug = slug
                while (CONTENT / category / f'{slug}.md').exists():
                    slug = f'{orig_slug}_{counter}'
                    counter += 1
            save_entry(category, slug, entry_data)
            self._send_json({'success': True, 'slug': slug})

        elif parsed.path == '/api/delete':
            category = data.get('category', 'books')
            slug = data.get('slug', '')
            ok = delete_entry(category, slug)
            self._send_json({'success': ok})

        elif parsed.path == '/api/build':
            output = run_build()
            push_result = git_push()
            self._send_json({'success': True, 'output': output, 'push': push_result})

        elif parsed.path == '/api/upload':
            result = handle_upload(data)
            if 'error' in result:
                self._send_json({'success': False, 'error': result['error']})
            else:
                self._send_json({'success': True, 'url': result['url']})

        else:
            self._send_json({'error': 'unknown endpoint'}, 404)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    print(f'🚀 启动服务器...')
    print(f'   网站地址: http://localhost:{PORT}')
    print(f'   后台管理: http://localhost:{PORT}/admin')
    print(f'   Ctrl+C 停止')
    print()
    server = http.server.HTTPServer(('0.0.0.0', PORT), AdminHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n⏹ 已停止')
        server.server_close()


if __name__ == '__main__':
    main()
