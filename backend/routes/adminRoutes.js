import express from "express";
import { protect } from "../middleware/authMiddleware.js";
import {
  createDepartment,
  createStaff,
  assignStaffToDepartment,
  getAnalytics,
  updateDepartment,
  deleteDepartment,
  getAuditLogs,
  getPredictiveStaffing,
  getStaffLoadBalancing
} from "../controllers/adminController.js";
import { getDepartments } from "../controllers/adminController.js";
import { getStaffUsers } from "../controllers/adminController.js";
import { getAllFeedback } from "../controllers/adminController.js";

const router = express.Router();

router.get("/departments", protect, getDepartments);
router.get("/staff", protect, getStaffUsers);
router.get("/analytics", protect, getAnalytics);
router.get("/audit-logs", protect, getAuditLogs);
router.get("/predictive-staffing", protect, getPredictiveStaffing);
router.get("/staff-load-balancing", protect, getStaffLoadBalancing);
// ==============================
// ADMIN: VIEW STUDENT FEEDBACK
// ==============================
router.get("/feedback", protect, getAllFeedback);


// Admin: create department
router.post("/departments", protect, createDepartment);
router.put("/departments/:id", protect, updateDepartment);
router.delete("/departments/:id", protect, deleteDepartment);

// Admin: create staff account
router.post("/staff", protect, createStaff);

// Admin: assign staff to department
router.post("/assign-staff", protect, assignStaffToDepartment);

export default router;
