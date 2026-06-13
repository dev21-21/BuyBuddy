// src/app/api/deals/route.js
import { MongoClient } from 'mongodb';

const uri = process.env.MONGO_URI;
const client = new MongoClient(uri);

export async function GET() {
  try {
    await client.connect();
    const db = client.db('deal_db');
    const deals = db.collection('deals');

    // 1. Query: Only verified, has image, has discount > 0
    // 2. Sort: Best discount first, then newest
    // 3. Project: Send only what UI needs (save bandwidth)
    const data = await deals.find(
      { 
        status: 'verified', 
        discount_percentage: { $gt: 5 }, // Filter noise (e.g. 1% off)
        sale_price: { $exists: true, $ne: null },
        image_url: { $exists: true, $ne: null, $ne: "" } // MUST have image
      },
      { 
        projection: { 
          _id: 0, // Hide Mongo ID
          product_name: 1, 
          sale_price: 1, 
          original_price: 1, 
          discount_percentage: 1, 
          currency: 1, 
          image_url: 1, 
          affiliate_link: 1,
          canonical_link: 1
        } 
      }
    )
    .sort({ discount_percentage: -1, extracted_at: -1 })
    .limit(50)
    .toArray();

    return Response.json(data);
  } catch (e) {
    console.error("API Error:", e);
    return Response.json({ error: 'Failed to fetch deals' }, { status: 500 });
  } finally {
    // In serverless (Vercel), don't close pool globally, but for safety:
    // await client.close(); 
  }
}