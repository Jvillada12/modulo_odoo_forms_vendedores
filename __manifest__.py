{
    'name': 'Website Vendor Order Form',
    'version': '1.0',
    'category': 'Website/Sales',
    'summary': 'Formulario web para que los vendedores generen pedidos',
    'description': '''
        Este módulo permite a los vendedores crear un formulario web (landing page)
        para mostrar productos a los clientes, permitiéndoles realizar pedidos
        con restricciones de inventario y asignación automática al vendedor.
    ''',
    'author': 'Tu Empresa',
    'website': 'https://www.tuempresa.com',
    'depends': [
        'base',
        'website',
        'sale_management',
        'stock',
        'crm',
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/templates.xml',
        'views/vendor_order_views.xml',
        'data/website_menu.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_vendor_order_form/static/src/js/vendor_order_form.js',
            'website_vendor_order_form/static/src/scss/vendor_order_form.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
