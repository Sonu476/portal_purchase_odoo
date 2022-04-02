from odoo import models, fields, api, _
from odoo.addons.website_sale_stock.models.sale_order import SaleOrder as WebsiteSaleStock
from odoo.http import request

from datetime import datetime, timedelta
from odoo.exceptions import MissingError
from lxml import etree
# from odoo.osv.orm import setup_modifiers
import decimal,re
from odoo.exceptions import except_orm, Warning, RedirectWarning, UserError
import logging
_logger = logging.getLogger(__name__)

manager_fields = []


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def tender_related_order(self,tender_id):
        count=0
        partner = request.env.user.partner_id
        print("testing..........")
        vendor_related = request.env['purchase.order'].sudo().search([('partner_id','=',partner.id)])
        vendor_count = request.env['purchase.order'].sudo().search_count([('partner_id','=',partner.id)])
        print("search Count",vendor_count)

        # vendors = vendor_related.id

        for vendor in vendor_related:
            print("vendors")
            count = count+1
            related_order = request.env['purchase.order'].sudo().browse(vendor.id)
            print("related_order tender_id",related_order.requisition_id)
            print("send tender_id",tender_id)
            if related_order.requisition_id.id == tender_id:
                print("achieved")
                return related_order
            else:
                if count == 4:
                    return None
                continue








    @api.model
    def purchase_tender(self):

        tender_count = request.env['purchase.requisition'].sudo().search_count([])
        return tender_count

    @api.model
    def quotation_count(self):
        partner = request.env.user.partner_id
        vendor_count = request.env['purchase.order'].sudo().search_count([('partner_id', '=', partner.id)])
        return vendor_count

class purchase(models.Model):
    _inherit = "purchase.order"

    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s %s' % (self.type_name, self.name)

    @api.depends('state')
    def _compute_type_name(self):
        for record in self:
            record.type_name = _('Quotation') if record.state in ('draft', 'sent', 'cancel') else _(
                    'Purchase Order')

    type_name = fields.Char('Type Name', compute='_compute_type_name')




        # signature........

    def _get_default_require_signature(self):
        return self.env.company.portal_confirmation_sign

    require_signature = fields.Boolean('Online Signature', default=_get_default_require_signature, readonly=True,
                                           states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
                                           help='Request a online signature to the customer in order to confirm orders automatically.')

    signature = fields.Image('Signature', help='Signature received through the portal.', copy=False,
                                 attachment=True, max_width=1024, max_height=1024)
    signed_by = fields.Char('Signed By', help='Name of the person that signed the SO.', copy=False)
    signed_on = fields.Datetime('Signed On', help='Date of the signature.', copy=False)

    def action_draft(self):
        orders = self.filtered(lambda s: s.state in ['cancel', 'sent'])
        return orders.write({
                'state': 'draft',
                'signature': False,
                'signed_by': False,
                'signed_on': False,
            })

    def has_to_be_signed(self, include_draft=False):
        return (self.state == 'sent' or (
                        self.state == 'draft' and include_draft)) and not self.is_expired and self.require_signature and not self.signature




class ResCompany(models.Model):
    _inherit = "res.company"

    portal_confirmation_sign = fields.Boolean(string='Online Signature', default=True)
    portal_confirmation_pay = fields.Boolean(string='Online Payment')
    quotation_validity_days = fields.Integer(default=30, string="Default Quotation Validity (Days)")





class PurchaseRequisition(models.Model):
    _inherit = "purchase.requisition"

    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s %s' % (self.type_name, self.name)

    @api.depends('state')
    def _compute_type_name(self):
        for record in self:
            record.type_name = _('Closed tender') if record.state in ('draft', 'sent', 'cancel') else _(
                    'Open tender')

    type_name = fields.Char('Type Name', compute='_compute_type_name')