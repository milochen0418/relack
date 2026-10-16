import reflex as rx
import os
from dotenv import load_dotenv

load_dotenv()

config = rx.Config(
    app_name="relack",
    google_client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    plugins=[
        rx.plugins.TailwindV3Plugin(
            config={
                "plugins": ["@tailwindcss/typography@0.5.20"],
                # Reflex 0.10 compiles memoized components into .web/app_components,
                # which the plugin's default content globs miss, so their classes
                # would never be generated.
                "content": [
                    "./app/**/*.{js,ts,jsx,tsx}",
                    "./utils/**/*.{js,ts,jsx,tsx}",
                    "./app_components/**/*.{js,ts,jsx,tsx}",
                ],
            },
        ),
        rx.plugins.sitemap.SitemapPlugin(),
        rx.plugins.RadixThemesPlugin(theme=rx.theme(appearance="light")),
    ],
)
