"""Playwright Chrome setup and bounded human-like interaction helpers."""

from __future__ import annotations

import random
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrowserProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str = "chrome"
    headless: bool = False
    locale: str = "vi-VN"
    timezone_id: str = "Asia/Ho_Chi_Minh"
    user_agent: str
    min_width: int = Field(default=1280, ge=800)
    max_width: int = Field(default=1920, ge=800)
    min_height: int = Field(default=800, ge=600)
    max_height: int = Field(default=1080, ge=600)

    def viewport(self, rng: random.Random | None = None) -> dict[str, int]:
        source = rng or random.SystemRandom()
        return {
            "width": source.randint(self.min_width, self.max_width),
            "height": source.randint(self.min_height, self.max_height),
        }


def launch_chrome(
    playwright: Any,
    profile: BrowserProfile,
    *,
    rng: random.Random | None = None,
) -> tuple[Any, Any]:
    """Launch installed Chrome with an explicit real-browser profile."""

    browser = playwright.chromium.launch(
        channel=profile.channel,
        headless=profile.headless,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=profile.user_agent,
        viewport=profile.viewport(rng),
        locale=profile.locale,
        timezone_id=profile.timezone_id,
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return browser, context


async def launch_async_chrome(
    playwright: Any,
    profile: BrowserProfile,
    *,
    rng: random.Random | None = None,
) -> tuple[Any, Any]:
    """Launch Chrome through Playwright's async API for the production worker."""

    browser = await playwright.chromium.launch(
        channel=profile.channel,
        headless=profile.headless,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        user_agent=profile.user_agent,
        viewport=profile.viewport(rng),
        locale=profile.locale,
        timezone_id=profile.timezone_id,
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


def human_click(
    page: Any,
    locator: Any,
    *,
    rng: random.Random | None = None,
    sleep: Any = time.sleep,
) -> None:
    """Scroll, wait for readiness, move the pointer, then click."""

    source = rng or random.SystemRandom()
    page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'})")
    sleep(source.uniform(1.5, 4.0))
    locator.wait_for(state="visible")
    sleep(source.uniform(0.5, 1.5))
    box = locator.bounding_box()
    if box:
        page.mouse.move(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2,
            steps=source.randint(5, 15),
        )
    locator.click()
