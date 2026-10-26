#!/usr/bin/env python3
"""
Offline regression tests for student query routing (no server, database or LLM required).

Usage:
    python -m unittest test_resources/test_student_query_routing.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.structured_query as sq

OWN_ID = "STU001"


class StudentQueryRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_names = sq._known_student_names
        sq._known_student_names = lambda: [("STU001", "aarav patel"), ("STU002", "priya sharma"), ("STU007", "rahul verma")]

    @classmethod
    def tearDownClass(cls):
        sq._known_student_names = cls._orig_names

    def route(self, query):
        if sq.is_student_restricted_query(query, OWN_ID):
            return "blocked"
        return sq.classify_student_query(query)

    def assertRoutes(self, expected, queries):
        for q in queries:
            with self.subTest(query=q):
                self.assertEqual(self.route(q), expected)

    def test_own_profile_questions_resolve_deterministically(self):
        self.assertRoutes("profile", [
            "What is my CGPA?",
            "Show my profile",
            "Do I have any backlogs?",
            "What is my placement status?",
            "Am I placed?",
            "Which company am I placed in?",
            "Tell me about Aarav Patel",
        ])

    def test_eligibility_questions_combine_record_and_circulars(self):
        self.assertRoutes("eligibility", [
            "Am I eligible for the Apex drive?",
            "Can I apply for the drive with my CGPA?",
            "Do I meet the 12th percentage criteria?",
        ])

    def test_circular_questions_are_not_blocked_or_answered_with_profile(self):
        # Previously these returned either the canned CGPA profile or an "Access Restricted" notice
        self.assertRoutes("public", [
            "What is the dress code for the interview?",
            "What is the last date to register for the placement drive?",
            "Which companies are visiting campus?",
            "Where is the training venue?",
            "What is the CTC offered by Apex?",
            "How many rounds are there in the selection process?",
            "What is the minimum CGPA required?",
            "What is the highest package offered?",
            "What are the eligibility criteria?",
            "What documents should I carry?",
            "When is the online assessment?",
            "What percentage is required in 12th?",
        ])

    def test_peer_and_aggregate_questions_are_blocked(self):
        self.assertRoutes("blocked", [
            "How many students are placed?",
            "How many got placed?",
            "Who has the highest CGPA?",
            "What is Priya Sharma's CGPA?",
            "Show STU002 record",
            "What is my rank in the batch?",
            "List all students with backlogs",
            "What is the average CGPA of the class?",
        ])


if __name__ == "__main__":
    unittest.main()
