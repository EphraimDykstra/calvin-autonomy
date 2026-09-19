import tempfile,unittest
from pathlib import Path
from engineering_assistant.plots import _padded_bounds,render_line_plot

class PlotTests(unittest.TestCase):
 def test_grayscale_line_plot_is_png(self):
  with tempfile.TemporaryDirectory() as d:
   out=render_line_plot({'title':'Performance','x_label':'Speed [RPM]','y_label':'Power [kW]','series':[{'name':'Power','x':[1000,2000,3000],'y':[1,3,2]}]},Path(d)/'plot.png')
   self.assertEqual(out.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
 def test_plot_rejects_bad_or_nonfinite_data(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError): render_line_plot({'series':[{'x':[1,2],'y':[1,float('nan')]}]},Path(d)/'bad.png')

 def test_relationship_plot_sorts_x_values_by_default(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); common={'title':'Efficiency','x_label':'Power [kW]','y_label':'Efficiency [%]'}
   unsorted=render_line_plot({**common,'series':[{'name':'Efficiency','x':[3,1,2],'y':[30,10,20]}]},root/'unsorted.png')
   sorted_plot=render_line_plot({**common,'series':[{'name':'Efficiency','x':[1,2,3],'y':[10,20,30]}]},root/'sorted.png')
   self.assertEqual(unsorted.read_bytes(),sorted_plot.read_bytes())

class AxisPaddingTests(unittest.TestCase):
 """A non-negative quantity must never be given a negative axis bound.

 A real run drew a -1116 K^2 gridline on a sum-of-squared-error plot, because
 the axis was padded by a flat 10% of the data range below the minimum.  A
 squared error cannot be negative, and a reader who sees one has been given a
 reason to doubt the rest of the figure.
 """
 def test_non_negative_data_is_never_padded_below_zero(self):
  lower,upper=_padded_bounds(0.5,1116.0,0.1)
  self.assertEqual(lower,0.0)
  self.assertGreater(upper,1116.0)

 def test_padding_that_does_not_cross_zero_is_left_alone(self):
  lower,_=_padded_bounds(100.0,500.0,0.1)
  self.assertAlmostEqual(lower,60.0)

 def test_genuinely_negative_data_is_still_padded_below_its_minimum(self):
  lower,_=_padded_bounds(-20.0,80.0,0.1)
  self.assertAlmostEqual(lower,-30.0)

if __name__=='__main__': unittest.main()
