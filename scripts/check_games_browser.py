"""Real browser smoke checks for all six games; no CDN or login required.

Run with the project's Playwright-enabled Python. Anonymous play does not
write account scores. --screenshots captures desktop/mobile entry screens.
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

NAMES = ['bird-guess', 'bird-runner', 'wetland-restorer', 'migration', 'wetland-detective', 'floating-island']


async def main(args):
    origin = urlsplit(args.base).netloc
    screenshots = Path(args.screenshots) if args.screenshots else None
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge')
        context = await browser.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
        external = []

        async def offline(route):
            if urlsplit(route.request.url).netloc != origin:
                external.append(route.request.url)
                await route.abort()
            else:
                await route.continue_()
        await context.route('**/*', offline)

        async def check(name):
            page = await context.new_page()
            errors, failed = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: failed.append([response.status, response.url]) if response.status >= 400 else None)
            try:
                await page.goto(args.base.rstrip('/') + '/' + name + '/', wait_until='load')
                if name == 'bird-guess':
                    await page.wait_for_function('!document.getElementById("quizStart").disabled')
                else:
                    await page.wait_for_function('!!document.getElementById("gameCanvas").width')
                if screenshots:
                    await page.screenshot(path=str(screenshots / (name + '-desktop.png')))
                for width in [390, 320]:
                    await page.set_viewport_size({'width': width, 'height': 844})
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), name + ' horizontal overflow'
                    if screenshots and width == 390:
                        await page.screenshot(path=str(screenshots / (name + '-mobile.png')))
                await page.set_viewport_size({'width': 1280, 'height': 900})

                if name == 'bird-guess':
                    await page.locator('#quizStart').click()
                    await page.locator('.mode-card.easy').click()
                    for index in range(10):
                        await page.wait_for_function('game.currentImageReady')
                        assert await page.locator('#birdImage').evaluate('(e)=>e.naturalWidth>0')
                        answer = await page.evaluate('game.questions[game.current].name')
                        await page.get_by_role('button', name=answer, exact=True).click()
                        await page.locator('#scienceSheet.show').wait_for(state='visible')
                        await page.locator('.science-close').click()
                        if index < 9:
                            await page.locator('#nextBtn').click()
                        else:
                            await page.locator('#finishBtn').click()
                    assert await page.locator('#resultScreen').is_visible()
                    assert await page.locator('#correctCount').inner_text() == '10'
                    state = {'questions_completed': 10, 'score': await page.locator('#finalScore').inner_text()}
                elif name == 'wetland-restorer':
                    await page.locator('#wrStartBtn').click()
                    await page.locator('.wr-level-card:not(.locked)').first.click()
                    await page.wait_for_function('wetlandGame.isRunning')
                    initial = await page.evaluate('wetlandGame.boat.x')
                    await page.keyboard.down('ArrowRight')
                    await page.wait_for_function('wetlandGame.boat.x > ' + str(initial + 1))
                    await page.keyboard.up('ArrowRight')
                    await page.locator('#wrToolClean').click()
                    assert await page.evaluate('wetlandGame.currentTool') == 'clean'
                    await page.locator('#gameCanvas').focus()
                    await page.keyboard.press('Space')
                    assert await page.evaluate('wetlandGame.currentTool') == 'algae'
                    await page.locator('#wrToolClean').click()
                    await page.locator('#wrFactBtn').click()
                    assert await page.locator('.wr-fact-card').count() > 0
                    state = {'running': True, 'boat_moved': True, 'tool': 'clean'}
                elif name == 'bird-runner':
                    await page.locator('.br-skin-card').nth(1).click()
                    assert await page.locator('.br-skin-card').nth(1).get_attribute('aria-pressed') == 'true'
                    await page.locator('#startOverlay .g-btn').click()
                    await page.wait_for_function('runnerGame.isRunning')
                    await page.keyboard.down('Space')
                    frame = await page.evaluate('runnerGame.frameCount')
                    await page.wait_for_function('runnerGame.frameCount>' + str(frame + 10))
                    await page.keyboard.up('Space')
                    state = await page.evaluate('({running:runnerGame.isRunning,bird:runnerGame.currentSkin.id,frame:runnerGame.frameCount})')
                    assert state['running']
                elif name == 'migration':
                    await page.locator('.mg-bird-card').nth(1).click()
                    await page.locator('#startOverlay .g-btn').click()
                    await page.wait_for_function('migrationGame.isRunning&&migrationGame.frameCount>10')
                    await page.locator('#mgFactBtn').click()
                    assert await page.locator('.mg-fact-card').count() > 0
                    state = await page.evaluate('({running:migrationGame.isRunning,selection:migrationGame.selectedBirdIndex,distance:migrationGame.distance})')
                elif name == 'floating-island':
                    await page.locator('#fiIslandCountSlider').fill('4')
                    assert await page.locator('#fiIslandCountStat').inner_text() == '4'
                    await page.locator('#startOverlay .g-btn').click()
                    await page.wait_for_function('floatingGame.isRunning')
                    assert await page.evaluate('floatingGame.islands.length') == 4
                    point = await page.evaluate('({x:floatingGame.islands[0].x+floatingGame.islands[0].w/2,y:floatingGame.islands[0].y+floatingGame.islands[0].h/2})')
                    await page.locator('#gameCanvas').click(position=point)
                    assert await page.evaluate('floatingGame.islands[0].items.length') > 0
                    await page.locator('#fiFactBtn').click()
                    state = {'running': True, 'islands': 4, 'item_placed': True}
                else:
                    await page.locator('#startOverlay .g-btn').click()
                    await page.wait_for_function('detective.isRunning')
                    for index in range(3):
                        point = await page.evaluate('({x:detective.hotspots[' + str(index) + '].displayX,y:detective.hotspots[' + str(index) + '].displayY})')
                        await page.locator('#gameCanvas').click(position=point)
                    await page.locator('#dtcOptionsPanel.show').wait_for(state='visible')
                    correct = await page.evaluate('detective._currentOptions.findIndex(b=>b.id===detective.currentCase.id)')
                    await page.locator('.dtc-option-card[data-idx="' + str(correct) + '"]').click()
                    await page.locator('#dtcScienceOverlay.show').wait_for(state='visible')
                    await page.locator('#dtcNextBtn').click()
                    await page.wait_for_function('detective.currentCaseIndex===1')
                    state = {'clues_collected': 3, 'answer_completed': True, 'next_case': 2}
                assert not errors, errors
                assert not failed, failed
                if screenshots:
                    await page.screenshot(path=str(screenshots / (name + '-playing.png')))
                print(json.dumps({'game': name, 'ok': True, 'state': state, 'js_errors': errors}, ensure_ascii=True), flush=True)
            finally:
                await page.close()

        for name in NAMES:
            await check(name)
        assert not external, external
        print('All six games passed without external network requests.', flush=True)

        # Failure states reproduce the reported "cannot open" experience.
        # These contexts contain no login token and never touch account scores.
        fault_context = await browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        await fault_context.route('**/*', offline)
        page = await fault_context.new_page()
        api_pattern = '**/api/games/birds/'
        await page.route(api_pattern, lambda route: route.fulfill(status=503, content_type='application/json', body='{}'))
        await page.goto(args.base.rstrip('/') + '/bird-guess/', wait_until='load')
        await page.locator('#quizRetry').wait_for(state='visible')
        assert await page.locator('#quizStart').is_disabled()
        await page.unroute(api_pattern)
        await page.locator('#quizRetry').click()
        await page.wait_for_function('!document.getElementById("quizStart").disabled')

        await page.route('**/media/**', lambda route: route.abort())
        await page.locator('#quizStart').click()
        await page.locator('.mode-card.easy').click()
        await page.locator('#imageRetry').wait_for(state='visible')
        assert await page.locator('.option-btn:disabled').count() == 4
        await page.unroute('**/media/**')
        await page.locator('#imageRetry').click()
        await page.wait_for_function('game.currentImageReady')
        print('Quiz API failure/retry and image failure/retry passed.', flush=True)
        await page.close()

        await fault_context.add_init_script("localStorage.setItem('wr_best_scores','{broken');localStorage.setItem('wr_best_stars','[]');localStorage.setItem('wr_unlocked','NaN');")
        page = await fault_context.new_page()
        await page.goto(args.base.rstrip('/') + '/wetland-restorer/', wait_until='load')
        await page.locator('#wrStartBtn').click()
        await page.locator('.wr-level-card:not(.locked)').first.click()
        assert await page.evaluate('wetlandGame.isRunning')
        await page.close()
        print('Corrupt restoration progress does not block starting.', flush=True)
        await fault_context.close()

        private_context = await browser.new_context()
        await private_context.route('**/*', offline)
        await private_context.add_init_script("Storage.prototype.getItem=function(){throw new DOMException('Storage blocked','SecurityError')};Storage.prototype.setItem=function(){throw new DOMException('Storage blocked','SecurityError')};")
        page = await private_context.new_page()
        await page.goto(args.base.rstrip('/') + '/bird-runner/', wait_until='load')
        await page.locator('.br-skin-card').nth(1).click()
        await page.locator('#startOverlay .g-btn').click()
        assert await page.evaluate('runnerGame.isRunning')
        await private_context.close()
        print('Storage-denied play passed.', flush=True)
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8012')
    parser.add_argument('--screenshots')
    asyncio.run(main(parser.parse_args()))
