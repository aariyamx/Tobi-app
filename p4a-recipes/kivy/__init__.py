import os
import pythonforandroid.recipes.kivy as stock_module
from pythonforandroid.recipes.kivy import KivyRecipe as StockKivyRecipe
STOCK_DIR = os.path.dirname(stock_module.__file__)
KivyRecipe = type("KivyRecipe", (StockKivyRecipe,), {"python_depends": ["filetype"], "get_recipe_dir": lambda self: STOCK_DIR})
recipe = KivyRecipe()
