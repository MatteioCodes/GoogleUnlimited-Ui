"""Browser checks against the real local API and worker, using a fake uploader."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import Dashboard, LocalServer


def fixture_uploader(path):
    path.write_text(f'#!{sys.executable}\n'+'''import json,sys
from pathlib import Path
args=sys.argv[1:]
config=Path('gotohp.config')
if args[0]=='--config':
    config=Path(args[1]);args=args[2:]
if args[:2]==['creds','list']:
    print('* browser@example.test' if config.exists() else 'No credentials found')
elif args[:2]==['creds','add']:
    if sys.stdin.read().strip()!='local-test-cookie': sys.exit(1)
    config.write_text('local simulated account')
elif args[0]=='upload':
    print(json.dumps({'total':1,'succeeded':1,'failed':0,'results':[{'path':args[-1],'success':True,'mediaKey':'browser-test'}]}))
else: sys.exit(1)
''')
    path.chmod(0o700)


def main():
    from playwright.sync_api import sync_playwright, expect
    from PIL import Image, ImageDraw
    screenshots=Path(os.environ.get('UI_SCREENSHOT_DIR',tempfile.mkdtemp(prefix='googleunlimited-ui-')))
    screenshots.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='googleunlimited-browser-') as directory:
        root=Path(directory)
        uploader=root/'gotohp-cli'
        fixture_uploader(uploader)
        selected=root/"Holiday's photos 📷"
        selected.mkdir()
        for index in range(8):
            image=Image.new('RGB',(480,360),['#bdd4cc','#c5d6e8','#dfd8bb','#b9cdb0'][index%4])
            draw=ImageDraw.Draw(image)
            draw.ellipse((295,40,365,110),fill='#f8e7b4')
            draw.polygon([(0,300),(190,130),(350,300),(480,220),(480,360),(0,360)],fill=['#6c9679','#718c9e','#b59c79','#7b9765'][index%4])
            image.save(selected/('First memory.jpg' if index==0 else f'Memory {index}.jpg'))
        app=Dashboard(root)
        server=LocalServer(('127.0.0.1',0),app)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('google-chrome'),headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];external=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                base=f'http://127.0.0.1:{server.server_port}'
                page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base) else None)
                page.goto(base)
                expect(page.locator('.setup-card')).to_be_visible()
                page.screenshot(path=str(screenshots/'library-empty.png'))
                page.locator('#backup-toggle').click()
                expect(page.locator('#account-dialog')).to_be_visible()
                page.locator('#oauth-token').fill('invalid-test-token')
                page.locator('#connect-button').click()
                expect(page.locator('#account-error')).to_contain_text('could not connect')
                page.locator('#oauth-token').fill('local-test-cookie')
                page.locator('#connect-button').click()
                expect(page.locator('#account-dialog')).not_to_be_visible()
                expect(page.locator('#oauth-token')).to_have_value('')
                page.get_by_role('link',name='Backup folders',exact=False).first.click()
                page.locator('.folder-add').click()
                page.locator('#folder-path').fill(str(root/'missing'))
                page.get_by_role('button',name='Go',exact=True).click()
                expect(page.locator('#browse-error')).to_be_visible()
                page.locator('#folder-path').fill(str(selected))
                page.get_by_role('button',name='Go',exact=True).click()
                expect(page.locator('#choose-folder')).to_be_enabled()
                page.locator('#choose-folder').click()
                expect(page.locator('#folder-dialog')).not_to_be_visible()
                expect(page.locator('.folder-row')).to_have_count(1)
                page.locator('#backup-toggle').click()
                expect(page.locator('#backup-toggle')).to_have_text('Pause backup')
                page.get_by_role('link',name='All photos',exact=False).click()
                expect(page.locator('.photo-card')).to_have_count(8,timeout=20000)
                page.get_by_role('button',name='Open First memory.jpg',exact=True).click()
                expect(page.locator('#preview-dialog')).to_be_visible()
                expect(page.locator('#preview-media img')).to_have_js_property('naturalWidth',480)
                page.keyboard.press('Escape')
                expect(page.locator('#preview-dialog')).not_to_be_visible()
                (selected/'Another memory.mp4').write_bytes(b'video-test')
                expect(page.locator('.photo-card')).to_have_count(9,timeout=15000)
                page.get_by_role('button',name='Videos',exact=True).click()
                expect(page.locator('.photo-card')).to_have_count(1)
                page.get_by_role('button',name='Photos',exact=True).click()
                expect(page.locator('.photo-card')).to_have_count(8)
                page.get_by_role('button',name='All photos',exact=True).click()
                page.locator('#global-search').fill('no such memory')
                expect(page.get_by_text('No photos found',exact=True)).to_be_visible()
                page.locator('#global-search').fill('First memory')
                expect(page.locator('.photo-card')).to_have_count(1)
                page.locator('#global-search').fill('')
                expect(page.locator('.photo-card')).to_have_count(9)
                page.mouse.move(0,0)
                page.screenshot(path=str(screenshots/'library-populated.png'))
                page.get_by_role('link',name='Settings',exact=True).first.click()
                page.locator('#theme-select').select_option('dark')
                expect(page.locator('html')).to_have_attribute('data-theme','dark')
                page.goto(base+'/#library')
                expect(page.locator('.photo-card')).to_have_count(9)
                expect(page.locator('html')).to_have_attribute('data-theme','dark')
                page.screenshot(path=str(screenshots/'library-dark.png'))
                page.locator('#backup-toggle').click()
                expect(page.locator('#backup-toggle')).to_have_text('Start backup')
                assert not app.running()
                page.set_viewport_size({'width':390,'height':844})
                for section in ('library','folders','activity','settings','help'):
                    page.goto(base+'/#'+section)
                    expect(page.locator('h1')).to_be_visible()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),section
                    if section=='library': page.screenshot(path=str(screenshots/'library-mobile.png'),full_page=True)
                page.get_by_role('button',name='Connect Google Photos',exact=False).click()
                page.locator('#oauth-token').fill('cleared-on-escape')
                page.keyboard.press('Escape')
                expect(page.locator('#oauth-token')).to_have_value('')
                assert not errors,errors
                assert not external,external
                browser.close()
                print('Browser checks passed: sign-in, folder browser, tiny images, real worker, image previews, video filter, search, themes, pause, keyboard handling, all mobile pages; no external requests or JavaScript errors.')
                print('Screenshots:',screenshots)
        finally:
            app.engine.stop()
            server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':main()
