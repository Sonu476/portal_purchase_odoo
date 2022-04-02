{
    'name': 'Portal_Purchase',
    'version': '1.2',
    'category': 'Operations/Purchase',
    'sequence': 60,
    'summary': 'Purchase orders, tenders and agreements',
    'description': "",
    'website': '',
    'depends': ['account','purchase','purchase_requisition'],
    'data': [
       'views/portal_templates.xml',
        'report/rport_.xml',
        'report/tender_report.xml',
        'views/purchase_order_inherit.xml',
    ],
    'demo': [
    ],
    'js':[],
    'installable': True,
    'auto_install': False,
    'application': True,
}