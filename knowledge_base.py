"""
knowledge_base.py
All product/shop data for HelloAgain AI (Nigeria).
To add a product: add a new dict to `business_data`.
"""

business_data = [
    # ── SHOP IDENTITY ─────────────────────────────────────
    {
        "category": "shop", "brand": "HelloAgain AI",
        "in_stock": True, "stock_count": None,
        "content": (
            "HelloAgain AI is a multi-category retail platform based in Lagos, Nigeria. "
            "We sell Tech, Fashion, Food, Home Appliances, Beauty, and more with fast nationwide "
            "delivery across all 36 states of Nigeria."
        ),
    },

    # ── TECH ──────────────────────────────────────────────
    {
        "category": "tech", "brand": "Samsung",
        "in_stock": True, "stock_count": 18,
        "image_url": "https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?auto=format&fit=crop&q=80&w=400",
        "content": (
            "Official partner. Galaxy S24 Ultra (NGN 1,800,000), S23 (NGN 1,300,000), "
            "A35 (NGN 480,000), A15 (NGN 260,000), Galaxy Tabs from NGN 420,000."
        ),
    },
    {
        "category": "tech", "brand": "Apple",
        "in_stock": True, "stock_count": 7,
        "image_url": "https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?auto=format&fit=crop&q=80&w=400",
        "content": (
            "iPhone 16 from NGN 1,650,000, iPhone 15 from NGN 1,300,000, "
            "MacBook Air M2/M3 from NGN 2,000,000, MacBook Pro from NGN 3,100,000, AirPods from NGN 145,000."
        ),
    },
    {
        "category": "tech", "brand": "HP & Lenovo",
        "in_stock": True, "stock_count": 14,
        "content": (
            "HP Pavilion (NGN 630,000+), Victus Gaming (NGN 1,100,000+), EliteBook from NGN 870,000. "
            "Lenovo IdeaPad from NGN 570,000, ThinkPad series available."
        ),
    },
    {
        "category": "tech", "brand": "Infinix Tecno and Itel",
        "in_stock": True, "stock_count": 35,
        "content": (
            "Infinix Hot series (NGN 75,000-200,000), Tecno Spark and Camon (NGN 65,000-280,000), "
            "Itel phones from NGN 45,000. Very popular budget phones."
        ),
    },
    {
        "category": "tech", "brand": "Accessories",
        "in_stock": True, "stock_count": 60,
        "content": (
            "Power banks (NGN 8,000-45,000), Earphones and Headphones (NGN 5,000-65,000), "
            "Phone cases and screen protectors (NGN 3,000-25,000), Bluetooth speakers (NGN 10,000-90,000), "
            "Laptop bags (NGN 12,000-48,000)."
        ),
    },
    {
        "category": "tech", "brand": "Smart TV",
        "in_stock": False, "stock_count": 0,
        "image_url": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?auto=format&fit=crop&q=80&w=400",
        "content": (
            "Smart TVs (Samsung, LG) 32-inch to 65-inch. Prices from NGN 330,000 to NGN 1,280,000. "
            "Currently out of stock; restock expected soon."
        ),
    },

    # ── FASHION ───────────────────────────────────────────
    {
        "category": "fashion", "brand": "Shirts and Tops",
        "in_stock": True, "stock_count": 80,
        "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&q=80&w=400",
        "content": (
            "Plain T-shirts (NGN 5,000-18,000), Polo shirts (NGN 9,000-25,000), "
            "Corporate and Oxford shirts (NGN 12,000-38,000). Custom printing and embroidery available."
        ),
    },
    {
        "category": "fashion", "brand": "Traditional Wear",
        "in_stock": True, "stock_count": 22,
        "content": (
            "Agbada, Senator, Dashiki, Kaftan, and Ankara styles. "
            "Prices from NGN 28,000 to NGN 180,000. Ready-made and made-to-measure options."
        ),
    },
    {
        "category": "fashion", "brand": "Footwear and Bags",
        "in_stock": True, "stock_count": 45,
        "image_url": "https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&q=80&w=400",
        "content": (
            "Sneakers (NGN 15,000-65,000), Corporate shoes (NGN 18,000-65,000), "
            "Ladies heels and flats (NGN 12,000-55,000), Quality handbags and backpacks (NGN 10,000-85,000)."
        ),
    },
    {
        "category": "fashion", "brand": "Jeans and Trousers",
        "in_stock": False, "stock_count": 0,
        "content": "Jeans and chinos (NGN 12,000-45,000). Currently out of stock; restock coming soon.",
    },

    # ── FOOD ──────────────────────────────────────────────
    {
        "category": "food", "brand": "Staples and Groceries",
        "in_stock": True, "stock_count": 200,
        "content": (
            "Rice (5kg NGN 7,500-12,500), Garri, Beans, Palm Oil, Spices, Yam, Plantain, "
            "Tomatoes, Onions. Wholesale and retail available."
        ),
    },
    {
        "category": "food", "brand": "Snacks",
        "in_stock": True, "stock_count": 150,
        "content": (
            "Chin Chin, Puff Puff, Plantain Chips, Groundnut, Biscuits, Cakes from NGN 1,500 per pack. "
            "Wholesale packages for events and schools."
        ),
    },
    {
        "category": "food", "brand": "Packaged Meals",
        "in_stock": True, "stock_count": 30,
        "content": (
            "Jollof Rice, Fried Rice, Egusi Soup with Fufu, Pounded Yam, Pepper Soup. "
            "Suitable for offices, events and home delivery in Lagos."
        ),
    },

    # ── HOME & APPLIANCES ─────────────────────────────────
    {
        "category": "home", "brand": "Appliances",
        "in_stock": True, "stock_count": 25,
        "content": (
            "Standing Fans (NGN 22,000-65,000), Blenders (NGN 18,000-55,000), Rice Cookers (NGN 15,000-42,000), "
            "Electric Kettles (NGN 9,000-25,000), Irons (NGN 11,000-32,000), Refrigerators from NGN 185,000."
        ),
    },

    # ── BEAUTY ────────────────────────────────────────────
    {
        "category": "beauty", "brand": "Cosmetics and Hair",
        "in_stock": True, "stock_count": 55,
        "content": (
            "Skincare (Nivea, Ponds, Olay), Hair extensions, Wigs, Makeup kits, "
            "Perfumes, Soaps, Lotions. Popular brands available at good prices."
        ),
    },

    # ── PAYMENT, DELIVERY & POLICIES ──────────────────────
    {
        "category": "payment", "brand": "Payment Options",
        "in_stock": True, "stock_count": None,
        "content": (
            "Bank Transfer, Opay, Palmpay, Flutterwave, Paystack, "
            "Cash on Delivery (Lagos only), Card payments in physical stores."
        ),
    },
    {
        "category": "delivery", "brand": "Nationwide Delivery",
        "in_stock": True, "stock_count": None,
        "content": (
            "Lagos: Same day or Next day (NGN 2,000-5,000). "
            "Other states: 2-5 business days (NGN 4,000-15,000 depending on weight and location). "
            "Tracking available."
        ),
    },
    {
        "category": "warranty", "brand": "Warranty Policy",
        "in_stock": True, "stock_count": None,
        "content": (
            "Tech and Home appliances come with minimum 3 months shop warranty plus "
            "manufacturer warranty where applicable. Fashion, Food and Beauty items are "
            "non-returnable except for defects."
        ),
    },
    {
        "category": "recommendation", "brand": "Special Offers",
        "in_stock": True, "stock_count": None,
        "content": (
            "We offer personalized recommendations based on budget and purpose. "
            "Students get special discounts on laptops, shirts, accessories and snacks. "
            "Bulk buyers enjoy wholesale pricing."
        ),
    },
]
