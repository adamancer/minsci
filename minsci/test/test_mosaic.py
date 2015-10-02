from minsci.mosaic import Mosaic

mosaic = Mosaic('')
mosaic.num_cols = 3

tiles = ['abc-1408-{}.jpg'.format(i) for i in xrange(1,100)]
print mosaic.sort_tiles(tiles)

tiles = [
    'abc_Grid[@0 0].jpg',
    'abc_Grid[@0 1].jpg',
    'abc_Grid[@0 2].jpg',
    'abc_Grid[@1 0].jpg',
    'abc_Grid[@1 1].jpg',
    'abc_Grid[@1 2].jpg',
    'abc_Grid[@2 0].jpg',
    'abc_Grid[@2 1].jpg',
    'abc_Grid[@2 2].jpg'
]
print mosaic.sort_tiles(tiles)
