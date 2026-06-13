// src/app/page.jsx
"use client";

import { useEffect, useState } from 'react';
import Image from 'next/image';

export default function Home() {
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/deals')
      .then(res => { if (!res.ok) throw new Error('Network error'); return res.json(); })
      .then(data => { setDeals(data); setLoading(false); })
      .catch(err => { console.error(err); setLoading(false); });
  }, []);

  if (loading) return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="text-center">
        <div className="text-4xl mb-4 animate-bounce">📦</div>
        <p className="text-xl font-bold text-gray-700">Hunting Best Deals...</p>
      </div>
    </div>
  );

  return (
    <main className="min-h-screen bg-gray-50 py-8 px-4">
      <header className="max-w-7xl mx-auto mb-10 text-center">
        <h1 className="text-4xl md:text-5xl font-extrabold text-orange-600 tracking-tight">BuyBuddy <span className="text-gray-800">🚀</span></h1>
        <p className="text-gray-500 mt-2 text-lg max-w-xl mx-auto">Verified, In-Stock & Sorted by Discount. No clickbait.</p>
      </header>

      <section className="max-w-7xl mx-auto">
        {deals.length === 0 ? (
          <div className="text-center text-gray-500 py-20">
            <p className="text-xl">No hot deals right now. 🕵️‍♂️</p>
            <p className="text-sm">Bot is scanning channels... Check back soon!</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {deals.map((deal) => (
              <DealCard key={deal.canonical_link || deal.original_link} deal={deal} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function DealCard({ deal }) {
  const { product_name, sale_price, original_price, discount_percentage, currency, image_url, affiliate_link } = deal;
  const sym = currency === 'INR' ? '₹' : '$';

  return (
    <a href={affiliate_link} target="_blank" rel="noopener noreferrer" className="group bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col h-full transition-all duration-300 hover:shadow-xl hover:-translate-y-1 hover:border-orange-200">
      {/* Discount Badge */}
      <div className="absolute top-3 right-3 z-10 bg-orange-500 text-white text-xs font-bold px-2.5 py-1 rounded-full shadow-lg">
        {discount_percentage}% OFF
      </div>

      {/* Image Container - Fixed Aspect Ratio */}
      <div className="relative h-56 bg-gray-100 overflow-hidden p-4 flex items-center justify-center">
        {image_url ? (
          <Image
            src={image_url}
            alt={product_name}
            fill
            className="object-contain transition-transform duration-500 group-hover:scale-105"
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
            loading="lazy"
            placeholder="blur"
            blurDataURL="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
          />
        ) : (
          <div className="text-6xl opacity-30">📦</div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 flex-1 flex flex-col d-flex">
        <h3 className="font-semibold text-gray-800 text-base line-clamp-2 h-12 mb-3 leading-snug">
          {product_name}
        </h3>
        
        <div className="mt-auto flex items-baseline gap-2">
          <span className="text-2xl font-black text-green-700">{sym}{sale_price?.toLocaleString()}</span>
          {original_price && (
            <span className="text-sm text-gray-400 line-through">{sym}{original_price.toLocaleString()}</span>
          )}
        </div>
      </div>

      {/* CTA Button */}
      <div className="p-4 pt-0 pb-4">
        <button className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-bold py-3 rounded-xl transition-all duration-200 shadow-lg shadow-orange-500/30 hover:shadow-orange-500/50 active:scale-[0.98]">
          Grab Deal 🛒
        </button>
      </div>
    </a>
  );
}