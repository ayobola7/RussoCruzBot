import pandas as pd
import numpy as np
import random
import yfinance as yf
from typing import Dict, List, Tuple
from strategy import RussoStrategy
import logging

logger = logging.getLogger(__name__)

class GeneticOptimizer:
    """Genetic Algorithm optimizer for RUSSO strategy per asset"""
    
    def __init__(self, symbol: str, period: str = '3mo', interval: str = '5m'):
        self.symbol = symbol
        self.period = period
        self.interval = interval
        self.population_size = 40
        self.generations = 25
        self.mutation_rate = 0.15
        self.crossover_rate = 0.7
        self.elitism_count = 4
        
        self.param_ranges = {
            'fast_length': (5, 30, int),
            'slow_length': (20, 100, int),
            'signal_length': (3, 20, int),
            'rsi_period': (7, 21, int),
            'rsi_oversold': (20, 40, int),
            'rsi_overbought': (60, 80, int),
            'volume_ma_period': (10, 50, int),
            'volume_threshold': (1.0, 2.0, float),
            'ema_trend_period': (20, 100, int),
            'min_confidence': (50, 80, int),
            'adx_threshold': (20, 40, int)
        }
    
    def fetch_data(self) -> pd.DataFrame:
        """Fetch historical data"""
        logger.info(f"Fetching {self.symbol} data for {self.period}")
        
        # Add '=X' for forex symbols if not present
        symbol = self.symbol
        if symbol in ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD']:
            symbol += '=X'
        
        df = yf.download(symbol, period=self.period, interval=self.interval)
        
        if df.empty:
            raise Exception(f"No data fetched for {self.symbol}")
        
        # Add synthetic volume if missing (for forex)
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            df['Volume'] = np.random.randint(1000, 10000, len(df))
        
        df.rename(columns={'Volume': 'volume'}, inplace=True)
        return df
    
    def create_individual(self) -> Dict:
        """Create random parameter set"""
        individual = {}
        for param, (min_val, max_val, param_type) in self.param_ranges.items():
            if param_type == int:
                individual[param] = random.randint(min_val, max_val)
            else:
                individual[param] = round(random.uniform(min_val, max_val), 2)
        
        # Ensure logical constraints
        if individual['slow_length'] <= individual['fast_length']:
            individual['slow_length'] = individual['fast_length'] + 10
        
        if individual['rsi_overbought'] <= individual['rsi_oversold']:
            individual['rsi_overbought'] = individual['rsi_oversold'] + 30
        
        if individual['adx_threshold'] < 20:
            individual['adx_threshold'] = 25
            
        return individual
    
    def calculate_fitness(self, params: Dict, df: pd.DataFrame) -> float:
        """Calculate fitness score for a parameter set"""
        try:
            strategy = RussoStrategy(params)
            df_indicators = strategy.calculate_indicators(df.copy())
            
            trades = []
            in_trade = False
            trade_entry = None
            trade_direction = None
            
            for i in range(len(df_indicators) - 1):
                if in_trade:
                    exit_price = df_indicators.iloc[i + 1]['close']
                    is_win = (exit_price > trade_entry) if trade_direction == 'CALL' else (exit_price < trade_entry)
                    
                    trades.append({
                        'win': is_win,
                        'profit': 8.5 if is_win else -10
                    })
                    in_trade = False
                    continue
                
                # Check for signal
                if i > 0:
                    signal = strategy.get_signal(df_indicators.iloc[:i+1], params['min_confidence'])
                    
                    if signal:
                        in_trade = True
                        trade_direction = signal['direction']
                        trade_entry = signal['entry_price']
            
            if not trades:
                return 0
            
            wins = sum(1 for t in trades if t['win'])
            win_rate = wins / len(trades) if trades else 0
            total_profit = sum(t['profit'] for t in trades)
            
            # Profit factor
            gross_profit = sum(t['profit'] for t in trades if t['profit'] > 0)
            gross_loss = abs(sum(t['profit'] for t in trades if t['profit'] < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 10
            
            # Sharpe ratio
            returns = [t['profit'] for t in trades]
            sharpe = np.mean(returns) / np.std(returns) if len(returns) > 1 and np.std(returns) > 0 else 0
            
            # Combined fitness
            fitness = (win_rate * 100) + (profit_factor * 10) + (sharpe * 5)
            
            # Penalty for too few trades
            if len(trades) < 15:
                fitness *= (len(trades) / 15)
            
            return fitness
            
        except Exception as e:
            logger.error(f"Fitness error: {e}")
            return 0
    
    def crossover(self, parent1: Dict, parent2: Dict) -> Dict:
        """Breed two parents"""
        child = {}
        for param in self.param_ranges.keys():
            if random.random() < self.crossover_rate:
                child[param] = parent1[param] if random.random() < 0.5 else parent2[param]
            else:
                child[param] = parent1[param]
        
        # Enforce constraints
        if child['slow_length'] <= child['fast_length']:
            child['slow_length'] = child['fast_length'] + 10
        
        if child['rsi_overbought'] <= child['rsi_oversold']:
            child['rsi_overbought'] = child['rsi_oversold'] + 30
        
        return child
    
    def mutate(self, individual: Dict) -> Dict:
        """Mutate an individual"""
        mutated = individual.copy()
        
        for param, (min_val, max_val, param_type) in self.param_ranges.items():
            if random.random() < self.mutation_rate:
                if param_type == int:
                    mutated[param] = random.randint(min_val, max_val)
                else:
                    mutated[param] = round(random.uniform(min_val, max_val), 2)
        
        # Enforce constraints
        if mutated['slow_length'] <= mutated['fast_length']:
            mutated['slow_length'] = mutated['fast_length'] + 10
        
        if mutated['rsi_overbought'] <= mutated['rsi_oversold']:
            mutated['rsi_overbought'] = mutated['rsi_oversold'] + 30
        
        return mutated
    
    def run_optimization(self) -> Tuple[Dict, float, Dict]:
        """Run genetic algorithm optimization"""
        logger.info(f"Starting optimization for {self.symbol}")
        
        df = self.fetch_data()
        train_size = int(len(df) * 0.7)
        train_df = df[:train_size]
        test_df = df[train_size:]
        
        # Initialize population
        population = [self.create_individual() for _ in range(self.population_size)]
        
        best_fitness = 0
        best_individual = None
        
        for generation in range(self.generations):
            # Calculate fitness
            fitness_scores = [self.calculate_fitness(ind, train_df) for ind in population]
            
            # Sort by fitness
            sorted_indices = np.argsort(fitness_scores)[::-1]
            population = [population[i] for i in sorted_indices]
            fitness_scores = [fitness_scores[i] for i in sorted_indices]
            
            # Update best
            if fitness_scores[0] > best_fitness:
                best_fitness = fitness_scores[0]
                best_individual = population[0].copy()
            
            logger.info(f"Gen {generation+1}: Best={fitness_scores[0]:.2f}, Avg={np.mean(fitness_scores):.2f}")
            
            # Create next generation
            next_population = []
            
            # Elitism
            next_population.extend(population[:self.elitism_count])
            
            # Crossover and mutation
            while len(next_population) < self.population_size:
                parent1 = random.choice(population[:20])
                parent2 = random.choice(population[:20])
                
                if random.random() < self.crossover_rate:
                    child = self.crossover(parent1, parent2)
                else:
                    child = parent1.copy()
                
                child = self.mutate(child)
                next_population.append(child)
            
            population = next_population
        
        # Validate on test data
        test_fitness = self.calculate_fitness(best_individual, test_df)
        
        return best_individual, best_fitness, {'train_fitness': best_fitness, 'test_fitness': test_fitness}
