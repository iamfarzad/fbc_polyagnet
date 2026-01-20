"""
Unit tests for MistakeAnalyzer self-learning system.

Run with: cd /Users/farzad/polyagent && python -m pytest agents/tests/test_mistake_analyzer.py -v
Or: cd /Users/farzad/polyagent/agents && python -c "import sys; sys.path.insert(0, '..'); exec(open('tests/test_mistake_analyzer.py').read())"
"""

import unittest
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import Mock, patch, MagicMock

from agents.utils.mistake_analyzer import MistakeAnalyzer, Lesson, POST_MORTEM_PROMPT


class TestLesson(unittest.TestCase):
    """Tests for Lesson dataclass"""
    
    def test_lesson_creation(self):
        """Test basic lesson creation"""
        lesson = Lesson(
            agent="safe",
            market_question="Will Bitcoin hit $100k?",
            original_reasoning="Strong momentum indicators",
            predicted_outcome="YES",
            actual_outcome="NO",
            pnl=-5.00,
            mistake_type="false_positive",
            lesson_learned="Don't trust momentum alone in range-bound markets"
        )
        
        self.assertEqual(lesson.agent, "safe")
        self.assertEqual(lesson.mistake_type, "false_positive")
        self.assertIsNotNone(lesson.id)  # Auto-generated
        self.assertIsNotNone(lesson.created_at)
    
    def test_lesson_id_unique(self):
        """Each lesson should have unique ID"""
        lesson1 = Lesson(agent="a", market_question="q", original_reasoning="r",
                        predicted_outcome="YES", actual_outcome="NO", pnl=0,
                        mistake_type="none", lesson_learned="l")
        lesson2 = Lesson(agent="a", market_question="q", original_reasoning="r",
                        predicted_outcome="YES", actual_outcome="NO", pnl=0,
                        mistake_type="none", lesson_learned="l")
        
        self.assertNotEqual(lesson1.id, lesson2.id)


class TestMistakeAnalyzer(unittest.TestCase):
    """Tests for MistakeAnalyzer class"""
    
    def setUp(self):
        """Set up mocks for each test"""
        self.patcher_supabase = patch('agents.utils.mistake_analyzer.get_supabase_state')
        self.mock_supabase = self.patcher_supabase.start()
        self.mock_supabase.return_value = None  # No Supabase by default
        
    def tearDown(self):
        self.patcher_supabase.stop()
    
    def test_analyzer_init(self):
        """Test analyzer initialization"""
        analyzer = MistakeAnalyzer(agent_name="safe")
        self.assertEqual(analyzer.agent_name, "safe")
    
    def test_get_resolved_trades_no_supabase(self):
        """Should return empty list without Supabase"""
        analyzer = MistakeAnalyzer(agent_name="safe")
        trades = analyzer.get_resolved_trades()
        self.assertEqual(trades, [])
    
    def test_format_lessons_empty(self):
        """Empty lessons should return empty string"""
        analyzer = MistakeAnalyzer(agent_name="safe")
        result = analyzer.format_lessons_for_prompt([])
        self.assertEqual(result, "")
    
    def test_format_lessons_with_data(self):
        """Lessons should be formatted correctly"""
        analyzer = MistakeAnalyzer(agent_name="safe")
        lessons = [
            {
                "mistake_type": "false_positive",
                "lesson_learned": "Don't trust hype alone",
                "market_question": "Will X happen by Y date?"
            }
        ]
        
        result = analyzer.format_lessons_for_prompt(lessons)
        
        self.assertIn("LESSONS FROM PAST MISTAKES", result)
        self.assertIn("FALSE_POSITIVE", result)
        self.assertIn("Don't trust hype alone", result)


class TestAnalyzeTrade(unittest.TestCase):
    """Tests for trade analysis with mocked LLM"""
    
    @patch('agents.utils.mistake_analyzer.OpenAI')
    @patch('agents.utils.mistake_analyzer.get_supabase_state')
    def test_analyze_winning_trade(self, mock_supa, mock_openai_class):
        """Winning trade should return 'none' mistake type"""
        # Mock Supabase to avoid errors
        mock_supa.return_value = MagicMock()
        
        # Mock the OpenAI response
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "was_correct": true,
            "mistake_type": "none",
            "lesson": "Good analysis, continue using this approach"
        }
        '''
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            analyzer = MistakeAnalyzer(agent_name="safe")
        
        trade = {
            "agent": "safe",
            "market_question": "Will Bitcoin hit $100k?",
            "outcome": "YES",
            "price": 0.60,
            "pnl": 5.00,
            "reasoning": "Strong momentum"
        }
        
        lesson = analyzer.analyze_trade(trade)
        
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.mistake_type, "none")
        self.assertEqual(lesson.pnl, 5.00)
    
    @patch('agents.utils.mistake_analyzer.OpenAI')
    @patch('agents.utils.mistake_analyzer.get_supabase_state')
    def test_analyze_losing_trade(self, mock_supa, mock_openai_class):
        """Losing trade should identify mistake type"""
        mock_supa.return_value = MagicMock()
        
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
        {
            "was_correct": false,
            "mistake_type": "false_positive",
            "lesson": "Momentum was not sufficient evidence"
        }
        '''
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            analyzer = MistakeAnalyzer(agent_name="safe")
        
        trade = {
            "agent": "safe",
            "market_question": "Will Bitcoin hit $100k?",
            "outcome": "YES",
            "price": 0.60,
            "pnl": -5.00,
            "reasoning": "Strong momentum"
        }
        
        lesson = analyzer.analyze_trade(trade)
        
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.mistake_type, "false_positive")
        self.assertLess(lesson.pnl, 0)


class TestRelevantLessons(unittest.TestCase):
    """Tests for fetching relevant lessons"""
    
    def test_keyword_matching(self):
        """Should rank lessons by keyword overlap"""
        with patch('agents.utils.mistake_analyzer.get_supabase_state') as mock_supa:
            mock_client = MagicMock()
            mock_supa.return_value = MagicMock()
            mock_supa.return_value.client = mock_client
            
            # Mock lessons
            mock_result = MagicMock()
            mock_result.data = [
                {"market_question": "Will Bitcoin hit $100k by 2026?", "lesson_learned": "L1"},
                {"market_question": "Will Ethereum merge succeed?", "lesson_learned": "L2"},
                {"market_question": "Will Bitcoin be banned?", "lesson_learned": "L3"},
            ]
            mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
            
            analyzer = MistakeAnalyzer(agent_name="safe")
            lessons = analyzer.get_relevant_lessons("Will Bitcoin reach $150k?", limit=2)
            
            # Bitcoin-related lessons should rank higher
            self.assertLessEqual(len(lessons), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
