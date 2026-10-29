# หน้าที่: กำหนดธีม พอร์ต และเรียก Streamlit
"""เปิด SmartBorrow พร้อมธีมแดงผ่านตัวเลือกมาตรฐานของ Streamlit.

รัน python run.py หรือ python run.py --server.port 8502
ธีมพื้นฐานอยู่ใน Python; HTML/CSS/JavaScript สำหรับหน้าตาอยู่ใน web_ui.py และ ui/
"""

from pathlib import Path
import sys
import argparse
import socket

from streamlit.web import cli

def requested_port(arguments):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--server.port',dest='port',type=int,default=8502)
    options,_=parser.parse_known_args(arguments)
    if not 1<=options.port<=65535:
        raise ValueError('พอร์ตต้องอยู่ระหว่าง 1–65535')
    return options.port

def port_in_use(port):
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        try:
            probe.bind(('127.0.0.1',port))
        except OSError as error:
            if error.errno in {98,48,10048} or getattr(error,'winerror',None)==10048:
                return True
            raise
    return False

def explain_busy_port(port):
    print(f'พอร์ต {port} มีโปรแกรมใช้งานอยู่แล้ว จึงไม่ได้เปิดเซิร์ฟเวอร์ซ้ำ')
    print(f'ถ้าเป็น SmartBorrow ที่เปิดไว้ ให้ใช้งานต่อที่ http://127.0.0.1:{port}/')
    print('หากต้องการเริ่มใหม่ ให้หยุดตัวรันเดิมก่อน แล้วค่อยกด F5 อีกครั้ง')


def main() -> None:
    """เรียก Streamlit CLI โดยกำหนดธีมและใช้การเชื่อมต่อภายในเครื่อง."""
    port=requested_port(sys.argv[1:])
    if port_in_use(port):
        explain_busy_port(port)
        return
    cli.main(
        args=[
            "run", str(Path(__file__).resolve().parent / "app.py"),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
            "--client.toolbarMode=minimal",
            "--ui.hideTopBar=false",
            "--theme.base=light",
            "--theme.primaryColor=#C51F41",
            "--theme.backgroundColor=#FFFFFF",
            "--theme.secondaryBackgroundColor=#F7F7F9",
            "--theme.textColor=#19191C",
            "--theme.font=SmartBorrow Thai",
            "--theme.headingFont=SmartBorrow Thai",
            "--theme.baseFontSize=16",
            "--theme.metricValueFontSize=2.25rem",
            "--theme.baseRadius=0.6rem",
            "--theme.buttonRadius=full",
            "--theme.borderColor=#E9E9EC",
            "--theme.showWidgetBorder=true",
            "--theme.showSidebarBorder=true",
            "--theme.dataframeHeaderBackgroundColor=#F9EDF0",
            "--theme.sidebar.backgroundColor=#FFF8FA",
            "--theme.sidebar.secondaryBackgroundColor=#F9E9EE",
            "--theme.sidebar.textColor=#472333",
            "--theme.sidebar.primaryColor=#C51F41",
            "--theme.sidebar.borderColor=#EED7E0",
            "--theme.redColor=#C82543",
            *sys.argv[1:],
        ],
        prog_name="streamlit",
    )


if __name__ == "__main__":
    main()
