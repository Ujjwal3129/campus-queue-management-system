// One-off script to create the first admin account.
//
// Usage (from the backend folder):
//   ADMIN_NAME="Your Name" ADMIN_EMAIL="you@example.com" ADMIN_PASSWORD="a-strong-password" \
//     node scripts/createAdmin.js
//
// Credentials are read from environment variables so they never appear in code
// or git history. MONGO_URI is loaded from backend/.env.

import dotenv from "dotenv";
import mongoose from "mongoose";
import bcrypt from "bcryptjs";
import User from "../models/User.js";

dotenv.config();

const { ADMIN_NAME, ADMIN_EMAIL, ADMIN_PASSWORD } = process.env;

if (!process.env.MONGO_URI) {
  console.error("MONGO_URI is not set (check backend/.env).");
  process.exit(1);
}
if (!ADMIN_NAME || !ADMIN_EMAIL || !ADMIN_PASSWORD) {
  console.error("Set ADMIN_NAME, ADMIN_EMAIL and ADMIN_PASSWORD environment variables.");
  process.exit(1);
}
if (ADMIN_PASSWORD.length < 8) {
  console.error("ADMIN_PASSWORD must be at least 8 characters.");
  process.exit(1);
}

try {
  await mongoose.connect(process.env.MONGO_URI);

  const existing = await User.findOne({ email: ADMIN_EMAIL });
  if (existing?.role === "admin") {
    // Safe to re-run: nothing is created or changed.
    console.log(`Admin already exists in database "${mongoose.connection.name}". Nothing changed.`);
  } else if (existing) {
    console.error("That email belongs to a non-admin user. Nothing changed.");
    process.exitCode = 1;
  } else {
    const hashed = await bcrypt.hash(ADMIN_PASSWORD, await bcrypt.genSalt(10));
    await User.create({
      fullName: ADMIN_NAME,
      email: ADMIN_EMAIL,
      password: hashed,
      role: "admin",
    });
    console.log(`Admin created in database "${mongoose.connection.name}".`);
  }
} catch (err) {
  console.error("Failed to create admin:", err.message);
  process.exitCode = 1;
} finally {
  await mongoose.disconnect();
}
