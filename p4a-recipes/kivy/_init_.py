   from pythonforandroid.recipes.kivy import KivyRecipe as StockKivyRecipe


   class KivyRecipe(StockKivyRecipe):
       python_depends = ["filetype"]


   recipe = KivyRecipe()
