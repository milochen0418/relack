import reflex as rx

config = rx.Config(
    app_name="relack",
    plugins=[
        rx.plugins.TailwindV3Plugin(),
        rx.plugins.sitemap.SitemapPlugin(),
    ],
)
