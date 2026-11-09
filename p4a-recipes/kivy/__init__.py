from pythonforandroid.recipes.kivy import KivyRecipe as StockKivyRecipe
KivyRecipe = type("KivyRecipe", (StockKivyRecipe,), {"python_depends": ["filetype"]})
recipe = KivyRecipe()
