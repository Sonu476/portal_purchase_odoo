from datetime import datetime
import base64
from collections import OrderedDict
import binascii
from odoo.addons.portal.controllers.mail import _message_post_helper

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.tools import image_process
from odoo.tools.translate import _
from odoo.addons.portal.controllers.portal import pager as portal_pager, CustomerPortal
from odoo.addons.web.controllers.main import Binary


class CustomerPortal(CustomerPortal):
    def _prepare_home_portal_values_quotation(self):
        values = super(CustomerPortal, self)._prepare_home_portal_values()
        values['quotation_count'] = request.env['purchase.order'].search_count([
            ('state', 'in', ['draft', 'sent'])
        ]) if request.env['purchase.order'].check_access_rights('read', raise_exception=False) else 0
        return values

    def _prepare_home_portal_values(self):
        values = super(CustomerPortal, self)._prepare_home_portal_values()
        values['purchase_count'] = request.env['purchase.order'].search_count([
            ('state', 'in', ['purchase', 'done', 'cancel'])
        ]) if request.env['purchase.order'].check_access_rights('read', raise_exception=False) else 0
        return values

    def _purchase_order_get_page_view_values(self, order, access_token, **kwargs):
        #
        def resize_to_48(b64source):
            if not b64source:
                b64source = base64.b64encode(Binary().placeholder())
            return image_process(b64source, size=(48, 48))

        values = {
            'order': order,
            'resize_to_48': resize_to_48,
        }
        return self._get_page_view_values(order, access_token, values, 'my_purchases_history', True, **kwargs)

    @http.route(['/my/purchase', '/my/purchase/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_purchase_orders(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        PurchaseOrder = request.env['purchase.order']
        tenders = request.env['purchase.requisition'].sudo().search([])

        domain = []

        archive_groups = self._get_archive_groups('purchase.order', domain) if values.get('my_details') else []
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name asc, id asc'},
            'amount_total': {'label': _('Total'), 'order': 'amount_total desc, id desc'},
        }
        # default sort by value
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        searchbar_filters = {
            'all': {'label': _('All'), 'domain': [('state', 'in', ['purchase', 'done', 'cancel'])]},
            'purchase': {'label': _('Purchase Order'), 'domain': [('state', '=', 'purchase')]},
            'cancel': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancel')]},
            'done': {'label': _('Locked'), 'domain': [('state', '=', 'done')]},
        }

        # searchbar_filters = {
        #     'all': {'label': _('All'), 'domain': [('state', 'in', ['draft','sent'])]},
        # }

        # default filter by value
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        # count for pager
        purchase_count = PurchaseOrder.search_count(domain)
        # make pager
        pager = portal_pager(
            url="/my/purchase",
            url_args={'date_begin': date_begin, 'date_end': date_end},
            total=purchase_count,
            page=page,
            step=self._items_per_page
        )
        # search the purchase orders to display, according to the pager data
        orders = PurchaseOrder.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )
        request.session['my_purchases_history'] = orders.ids[:100]

        values.update({
            'date': date_begin,
            'orders': orders,
            'page_name': 'purchase',
            'pager': pager,
            'archive_groups': archive_groups,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
            'default_url': '/my/purchase',
            'tenders': tenders
        })
        return request.render("portal_purchase.portal_my_purchase_orders", values)

    @http.route(['/my/purchase/<int:order_id>'], type='http', auth="public", website=True)
    def portal_my_purchase_order(self, order_id=None, access_token=None,report_type=None,download=False,message=False, **kw):
        try:
            order_sudo = self._document_check_access('purchase.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=order_sudo, report_type=report_type,
                                     report_ref='purchase.action_report_purchase_order', download=download)

        # partner = request.env.user.partner_id
        # order_sudo = request.env['purchase.order'].sudo().search(['partner_id','=',partner] and ['requisition_id','=',order_id])

        values = self._purchase_order_get_page_view_values(order_sudo, access_token, **kw)
        if order_sudo.company_id:
            values['res_company'] = order_sudo.company_id
        return request.render("portal_purchase.sale_order_portal_template", values)



    @http.route(['/my/purchase/<int:order_id>/accept'], type='json', auth="public", website=True)
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        # get from query string if not on json param
        access_token = access_token or request.httprequest.args.get('access_token')

        try:
            order_sudo = self._document_check_access('purchase.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return {'error': _('Invalid order.')}

        # if not order_sudo.has_to_be_signed():
        #     return {'error': _('The order is not in a state requiring customer signature.')}
        # if not signature:
        #     return {'error': _('Signature is missing.')}

        try:
            order_sudo.write({
                'signed_by': name,
                'signed_on': fields.Datetime.now(),
                'signature': signature,
            })
            request.env.cr.commit()
        except (TypeError, binascii.Error) as e:
            return {'error': _('Invalid signature data.')}

        # if not order_sudo.has_to_be_paid():
        #     order_sudo.action_confirm()
        #     order_sudo._send_order_confirmation_mail()

        pdf = request.env.ref('purchase.action_report_purchase_order').sudo().render_qweb_pdf([order_sudo.id])[0]
        print("testing signature")

        _message_post_helper(
            'purchase.order', order_sudo.id, _('Order signed by %s') % (name,),
            attachments=[('%s.pdf' % order_sudo.name, pdf)],
            **({'token': access_token} if access_token else {}))

        query_string = '&message=sign_ok'
        # if order_sudo.has_to_be_paid(True):
        #     query_string += '#allow_payment=yes'
        return {
            'force_refresh': True,
            'redirect_url': order_sudo.get_portal_url(query_string=query_string),
        }







    @http.route(['/my/Quotation', '/my/Quotation/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_quotation_orders(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        values = self._prepare_home_portal_values_quotation()
        partner = request.env.user.partner_id
        PurchaseOrder = request.env['purchase.order']

        domain = []

        archive_groups = self._get_archive_groups('purchase.order', domain) if values.get('my_details') else []
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name asc, id asc'},
            'amount_total': {'label': _('Total'), 'order': 'amount_total desc, id desc'},
        }
        # default sort by value
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # searchbar_filters = {
        #     'all': {'label': _('All'), 'domain': [('state', 'in', ['purchase', 'done', 'cancel'])]},
        #     'purchase': {'label': _('Purchase Order'), 'domain': [('state', '=', 'purchase')]},
        #     'cancel': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancel')]},
        #     'done': {'label': _('Locked'), 'domain': [('state', '=', 'done')]},
        # }

        searchbar_filters = {
            'all': {'label': _('All'), 'domain': [('state', 'in', ['draft', 'sent'])]},
            'RFQ': {'label': _('RFQ'), 'domain': [('state', '=', 'draft')]},
            'RFQ sent': {'label': _('RFQ sent'), 'domain': [('state', '=', 'sent')]},

        }

        # default filter by value
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        # count for pager
        quotation_count = PurchaseOrder.search_count(domain)
        # make pager
        pager = portal_pager(
            url="/my/purchase",
            url_args={'date_begin': date_begin, 'date_end': date_end},
            total=quotation_count,
            page=page,
            step=self._items_per_page
        )
        # search the purchase orders to display, according to the pager data
        orders = PurchaseOrder.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )
        request.session['my_purchases_history'] = orders.ids[:100]

        values.update({
            'date': date_begin,
            'orders': orders,
            'page_name': 'purchase',
            'pager': pager,
            'archive_groups': archive_groups,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
            'default_url': '/my/purchase',
        })
        return request.render("portal_purchase.portal_my_purchase_quotations", values)

    @http.route(['/my/tender/<int:requisition_id>'], type='http', auth="public", website=True)
    def portal_my_purchase_tender(self, requisition_id=None, access_token=None,report_type=None,download=False,message=False, **kw):

        try:
            order_sudo = self._document_check_access('purchase.requisition', requisition_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=order_sudo, report_type=report_type,
                                     report_ref='portal_purchase.action_report_tender_order', download=download)

        values = self._purchase_order_get_page_view_values(order_sudo, access_token, **kw)

        if order_sudo.company_id:
            values['res_company'] = order_sudo.company_id
        return request.render("portal_purchase.tender_portal_template", values)

    @http.route('/purchase/price', type='http', auth='public', website=True)
    def price_update(self, access_token=None, **kw):

        lines = request.env['purchase.order'].sudo().browse(int(kw['order_id']))
        order_id = int(kw['order_id'])

        if lines.order_line.exists():
            print("available", )
            lines.order_line.state = "sent"
            print(lines.order_line.product_id)
            print(int(kw['product_id']))
            for rec in lines.order_line:
                print(rec)
                print("rec.product_id", rec.product_id.id)

                if int(kw['product_id']) == rec.product_id.id:
                    print("pass")

                    vals = {'product_uom_qty': kw['product_qty'], 'order_id': int(kw["order_id"]),
                            'product_uom': int(kw["product_uom"]),
                            'product_id': int(kw["product_id"]),
                            'price_unit': kw['price_unit'],
                            # 'customer_lead': kw['customer_lead'],
                            }
                    rec.write(vals)

                    return request.redirect(lines.get_portal_url())



    @http.route(['/purchase/edit/<int:order_id>'], type='http', auth="public", website=True)
    def price_edit(self, order_id=None, access_token=None, **kw):

        try:
            order_sudo = self._document_check_access('purchase.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._purchase_order_get_page_view_values(order_sudo, access_token, **kw)
        edit=1
        values['edit']=edit
        if order_sudo.company_id:
            values['res_company'] = order_sudo.company_id
        return request.render("portal_purchase.sale_order_portal_template", values)

    @http.route(['/create/quotation/<int:tender_id>'], type='http', auth="public", website=True)
    def create_quotation(self, tender_id=None, access_token=None, **kw):
        print("creating quotation")

        partner = request.env.user.partner_id
        country_id = request.env['res.partner'].sudo().search([('id', '=', partner.id)]).country_id
        print("country", country_id)

        currency_id = request.env['res.country'].browse(country_id.id).currency_id
        print(currency_id.name)

        origin = request.env['purchase.requisition'].sudo().search([('id', '=', tender_id)])
        line_ids = request.env['purchase.requisition'].sudo().search([('id', '=', tender_id)]).line_ids
        print("line_ids...", origin)

        vals = {
            'partner_id': partner.id,
            'requisition_id': tender_id,
            'date_order': datetime.date(datetime.now()),

            'origin': origin.name,
            'currency_id': currency_id.id,

        }
        order_id = request.env['purchase.order'].sudo().create(vals)
        print("quotation created", vals)
        # print("ordre_id.....",order_id)

        print("Order_id", order_id.name)

        lines = request.env['purchase.order'].sudo().browse(order_id.id)
        # order_id=int(kw['order_id'])
        line = origin.line_ids
        print(line)
        for rec in line:
            # lines.order_line.state = "sent"

            vals = {'product_qty': rec.product_qty,
                    'product_uom': rec.product_uom_id.id,
                    'product_id': rec.product_id.id,
                    'order_id': order_id.id,
                    'price_unit': rec.price_unit,
                    'name': rec.product_id.name,
                    'date_planned': rec.schedule_date,
                    # 'account_analytic_id':rec.account_analytic_id,
                    # 'currency_id':currency_id.id,

                    # 'customer_lead': kw['customer_lead'],
                    }
            lines.order_line.create(vals)
            print("completed")

        order_id = order_id.id
        try:
            order_sudo = self._document_check_access('purchase.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._purchase_order_get_page_view_values(order_sudo, access_token, **kw)
        edit = 1
        values['edit'] = edit
        if order_sudo.company_id:
            values['res_company'] = order_sudo.company_id
        return request.render("portal_purchase.sale_order_portal_template", values)



