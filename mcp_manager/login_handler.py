"""
Centralized login handler for all adapters.

Handles the login flow for any adapter by:
1. Reading login configuration from config.json
2. Creating a temporary persistent context for login
3. Waiting for user to complete login
4. Extracting and transferring cookies to the target context
5. Closing the login context
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)


class LoginHandler:
    """Centralized login handler for all adapters."""

    async def handle_login(
        self,
        task_name: str,
        target_context: BrowserContext,
        config: Dict[str, Any]
    ) -> bool:
        """
        Handle login flow for any adapter.

        Args:
            task_name: Name of the task (e.g., "thinking")
            target_context: The ephemeral context to transfer cookies to
            config: Task configuration from config.json

        Returns:
            True if login successful, False otherwise
        """
        login_config = config.get("login")
        if not login_config:
            logger.error(f"No login configuration found for task: {task_name}")
            return False

        login_url = login_config.get("url")
        profile_subdir = login_config.get("profile_subdir", f"{task_name}_login")
        success_indicators = login_config.get("success_indicators", {})
        timeout = login_config.get("timeout", 300)

        logger.info(f"Starting login flow for task: {task_name}")

        login_context = None
        try:
            # Create temporary persistent context for login
            from mcp_manager.browser import get_browser_config
            browser_config = get_browser_config()

            login_context = await browser_config.create_context(
                profile_subdir=profile_subdir,
                headless_override=False  # Visible window for user login
            )

            # Check if we already have valid cookies
            if await self._check_saved_cookies(login_context, target_context, config, success_indicators):
                logger.info("Found valid saved session, cookies transferred")
                await login_context.close()
                return True

            # Need to log in - open login window
            logger.info(f"No valid session found. Opening login window at: {login_url}")
            login_page = login_context.pages[0] if login_context.pages else await login_context.new_page()
            await login_page.goto(login_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Wait for user to complete login
            logger.info(f"Waiting up to {timeout} seconds for user login...")
            if not await self._wait_for_login(login_page, success_indicators, timeout):
                logger.error("Login timed out")
                await login_context.close()
                return False

            logger.info("Login successful! Extracting cookies...")

            # Navigate to the app URL to ensure we have all cookies
            app_url = config.get("url")
            if app_url and app_url not in login_page.url:
                await login_page.goto(app_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

            # Transfer cookies to target context
            await self._transfer_cookies(login_context, target_context)

            # Close login context (session saved in persistent profile)
            await login_context.close()
            logger.info("Login context closed, session saved")

            return True

        except Exception as e:
            logger.error(f"Login flow error: {e}", exc_info=True)
            if login_context:
                try:
                    await login_context.close()
                except:
                    pass
            return False

    async def _check_saved_cookies(
        self,
        login_context: BrowserContext,
        target_context: BrowserContext,
        config: Dict[str, Any],
        success_indicators: Dict[str, Any]
    ) -> bool:
        """
        Check if we have valid saved cookies in the persistent profile.

        Args:
            login_context: The persistent login context
            target_context: The ephemeral context to transfer cookies to
            config: Task configuration
            success_indicators: Success indicators from config

        Returns:
            True if valid cookies found and transferred, False otherwise
        """
        try:
            app_url = config.get("url")
            if not app_url:
                return False

            login_page = login_context.pages[0] if login_context.pages else await login_context.new_page()
            await login_page.goto(app_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Check if we're logged in using success indicators
            if await self._check_success(login_page, success_indicators):
                logger.info("Valid saved session detected")
                # Transfer cookies
                await self._transfer_cookies(login_context, target_context)
                return True

            return False

        except Exception as e:
            logger.warning(f"Error checking saved cookies: {e}")
            return False

    async def _wait_for_login(
        self,
        login_page: Page,
        success_indicators: Dict[str, Any],
        timeout: int
    ) -> bool:
        """
        Wait for user to complete login.

        Args:
            login_page: The login page
            success_indicators: Success indicators from config
            timeout: Max seconds to wait

        Returns:
            True if login successful, False if timed out
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                if await self._check_success(login_page, success_indicators):
                    return True
            except Exception as e:
                # Page might be navigating during login, ignore and retry
                logger.debug(f"Error checking login status: {e}")

            await asyncio.sleep(1)

        return False

    async def _check_success(
        self,
        page: Page,
        success_indicators: Dict[str, Any]
    ) -> bool:
        """
        Check if login was successful using configured indicators.

        Uses OR logic: success if ANY indicator matches.

        Args:
            page: The page to check
            success_indicators: Dict with 'titles', 'urls', 'selectors'

        Returns:
            True if any success indicator matches
        """
        try:
            # Check title
            titles = success_indicators.get("titles", [])
            if titles:
                page_title = await page.title()
                page_title = page_title.strip()
                if page_title in titles:
                    logger.info(f"Login success detected: title matches '{page_title}'")
                    return True

            # Check URL
            urls = success_indicators.get("urls", [])
            if urls:
                current_url = page.url
                for url_pattern in urls:
                    if url_pattern in current_url:
                        logger.info(f"Login success detected: URL contains '{url_pattern}'")
                        return True

            # Check selectors
            selectors = success_indicators.get("selectors", [])
            if selectors:
                for selector in selectors:
                    try:
                        count = await page.locator(selector).count()
                        if count > 0:
                            logger.info(f"Login success detected: found selector '{selector}'")
                            return True
                    except:
                        pass

            return False

        except Exception as e:
            logger.debug(f"Error checking success indicators: {e}")
            return False

    async def _transfer_cookies(
        self,
        source_context: BrowserContext,
        target_context: BrowserContext
    ) -> None:
        """
        Transfer cookies from source context to target context.

        Args:
            source_context: Context to extract cookies from
            target_context: Context to add cookies to
        """
        cookies = await source_context.cookies()
        logger.info(f"Extracted {len(cookies)} cookies from login session")

        await target_context.add_cookies(cookies)
        logger.info("Cookies transferred to target context")
