import { MongoClient } from 'mongodb';
import { NextResponse } from 'next/server';

const uri = process.env.MONGODB_URI;

export async function GET() {
    let client;
    try {
        if (!uri) {
            return NextResponse.json({ error: "MONGODB_URI is missing in .env.local" }, { status: 500 });
        }

        client = new MongoClient(uri);
        await client.connect();
        console.log("✅ Connected to MongoDB successfully");

        const database = client.db('deal_db');
        const deals = database.collection('deals');

        const sortedDeals = await deals
            .find({ product_name: { $ne: "Unknown Product" } }) // Filter out the messy ones
            .sort({ discount_percentage: -1, _id: -1 }) 
            .limit(50)
            .toArray();

        return NextResponse.json(sortedDeals);
    } catch (e) {
        console.error("🚨 API Error:", e);
        return NextResponse.json({ error: e.message }, { status: 500 });
    } finally {
        if (client) await client.close();
    }
}
