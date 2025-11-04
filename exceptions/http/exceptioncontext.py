from __future__ import annotations

def exceptions(error_message: str, formatted_traceback: str, underlined_line: str,
               error_type: str, file_and_line: str, code_lines: str,
               system_info: dict, req_data: dict = None):

    def dict_to_html(data: dict) -> str:
        return "<table class='info-table'>" + "".join(
            f"<tr><td class='key'>{k}</td><td class='value'>{v}</td></tr>"
            for k, v in data.items()
        ) + "</table>"

    system_info_content = dict_to_html(system_info)
    req_info = dict_to_html(req_data) if req_data else "<p>No request data available</p>"

    html_content = f"""
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{error_type}: {error_message}</title>
<style>
    :root {{
        --font: "Inter", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
        --mono: "JetBrains Mono", "SF Mono", "Consolas", monospace;

        --bg: #ffffff;
        --fg: #1c1e21;
        --muted: #65676b;
        --border: #dadce0;
        --accent: #0866ff;
        --surface: #f5f6f7;
        --code-bg: #f8f9fa;
        --error: #d93025;
        --error-bg: #fdecea;
    }}
    @media (prefers-color-scheme: dark) {{
        :root {{
            --bg: #0f0f10;
            --fg: #e4e6eb;
            --muted: #b0b3b8;
            --border: #3a3b3c;
            --accent: #2d88ff;
            --surface: #1c1e21;
            --code-bg: #18191a;
            --error: #ff6b5a;
            --error-bg: #2d1615;
        }}
    }}

    body {{
        margin: 0;
        background: var(--bg);
        color: var(--fg);
        font-family: var(--font);
        display: flex;
        flex-direction: column;
        min-height: 100vh;
    }}

    header {{
        background: var(--surface);
        border-bottom: 1px solid var(--border);
        padding: 16px 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        animation: fadeDown 0.4s ease;
    }}

    header h1 {{
        font-weight: 600;
        font-size: 18px;
        color: var(--error);
        margin: 0;
    }}

    header span {{
        font-size: 13px;
        color: var(--muted);
    }}

    main {{
        flex: 1;
        padding: 24px;
        animation: fadeIn 0.4s ease;
    }}

    footer {{
        border-top: 1px solid var(--border);
        text-align: center;
        color: var(--muted);
        font-size: 13px;
        padding: 12px 0;
    }}

    h2 {{
        font-size: 15px;
        font-weight: 600;
        margin: 24px 0 12px;
        color: var(--fg);
    }}

    pre {{
        background: var(--code-bg);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 14px 16px;
        font-family: var(--mono);
        font-size: 13px;
        white-space: pre-wrap;
        overflow-x: auto;
        line-height: 1.55;
        color: var(--fg);
    }}

    /* ===== Syntax Highlighting (pure CSS) ===== */
    pre .kw {{ color: #d73a49; font-weight: 600; }}       /* Keywords */
    pre .str {{ color: #0b7500; }}                         /* Strings */
    pre .num {{ color: #1c00cf; }}                         /* Numbers */
    pre .com {{ color: #6a737d; font-style: italic; }}     /* Comments */
    pre .errline {{ background: var(--error-bg); border-left: 3px solid var(--error); padding-left: 12px; display: block; }}

    details {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        margin-bottom: 16px;
        overflow: hidden;
    }}
    details summary {{
        padding: 12px 16px;
        cursor: pointer;
        font-weight: 500;
        font-size: 14px;
        color: var(--fg);
        list-style: none;
        user-select: none;
    }}
    details[open] summary {{
        background: var(--code-bg);
        border-bottom: 1px solid var(--border);
        color: var(--accent);
    }}
    details > pre, details > div {{
        padding: 16px;
    }}

    .info-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }}
    .info-table td {{
        padding: 6px 8px;
        border-bottom: 1px solid var(--border);
        vertical-align: top;
    }}
    .info-table .key {{
        color: var(--muted);
        width: 25%;
        font-weight: 500;
    }}

    @keyframes fadeIn {{
        from {{opacity: 0; transform: translateY(6px);}}
        to {{opacity: 1; transform: translateY(0);}}
    }}
    @keyframes fadeDown {{
        from {{opacity: 0; transform: translateY(-6px);}}
        to {{opacity: 1; transform: translateY(0);}}
    }}
    ::selection {{
        background: var(--accent);
        color: #fff;
    }}
</style>
</head>
<body>
<header>
    <h1>{error_type}</h1>
    <span>{file_and_line}</span>
</header>

<main>
    <section style="margin-bottom: 24px;">
        <h2>{error_message}</h2>
        <pre><span class='errline'>{underlined_line}</span></pre>
    </section>

    <details open>
        <summary>Formatted Traceback</summary>
        <pre>{formatted_traceback}</pre>
    </details>

    <details>
        <summary>Detailed Traceback</summary>
        <pre>{code_lines}</pre>
    </details>

    <details>
        <summary>Request Information</summary>
        <div>{req_info}</div>
    </details>

    <details>
        <summary>System Information</summary>
        <div>{system_info_content}</div>
    </details>
</main>

<footer>
    ⚙️ Powered by <b>Evelax</b> • Exception Inspector for <b>Bermoid</b>
</footer>
</body>
</html>
"""
    return html_content
