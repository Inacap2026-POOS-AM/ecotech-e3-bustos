class Proyecto:
    """Proyecto de EcoTech. La ciudad sirve para el clima y la moneda para los pagos."""

    def __init__(self, nombre, ciudad, pais, moneda, id=None):
        self.id = id
        self.nombre = nombre
        self.ciudad = ciudad
        self.pais = pais
        self.moneda = moneda
        self.empleados = []

    def __str__(self):
        return "%s - %s, %s (%s)" % (self.nombre, self.ciudad, self.pais, self.moneda)
