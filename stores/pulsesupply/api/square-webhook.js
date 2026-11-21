import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method Not Allowed' });

  const signature = req.headers['x-square-hmacsha256-signature'] || '';
  const sigKey = process.env.SQUARE_WEBHOOK_SIGNATURE_KEY || '';
  const notificationUrl = process.env.SQUARE_NOTIFICATION_URL || '';

  if (sigKey && notificationUrl) {
    const hmac = crypto.createHmac('sha256', sigKey);
    hmac.update(notificationUrl + JSON.stringify(req.body));
    if (signature !== hmac.digest('base64')) return res.status(401).json({ error: 'Invalid Square signature' });
  }

  const payment = req.body?.data?.object?.payment;
  if (req.body?.type !== 'payment.updated' || payment?.status !== 'COMPLETED') {
    return res.status(200).json({ ignored: true });
  }

  const shipping = payment?.shipping_address || {};
  const catalogPath = path.join(process.cwd(), 'catalog.json');
  const catalog = fs.existsSync(catalogPath) ? JSON.parse(fs.readFileSync(catalogPath, 'utf8')) : [];
  const amountDollars = (payment?.amount_money?.amount || 0) / 100;
  const matched = catalog.find(item => Math.abs(item.product.retail - amountDollars) < 0.05) || catalog[catalog.length - 1];

  if (!matched || !process.env.CJ_ACCESS_TOKEN) {
    return res.status(200).json({ warning: 'No matching SKU or CJ_ACCESS_TOKEN missing' });
  }

  const cjEndpoint = ['https://developers.cjdropshipping.com', 'api2.0/v1/shopping/order/createOrderV2'].join('/');
  const cjRes = await fetch(cjEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'CJ-Access-Token': process.env.CJ_ACCESS_TOKEN },
    body: JSON.stringify({
      orderNumber: payment.id,
      shippingZip: shipping.postal_code || '',
      shippingCountryCode: shipping.country || 'US',
      shippingCountry: 'United States',
      shippingProvince: shipping.administrative_district_level_1 || '',
      shippingCity: shipping.locality || '',
      shippingAddress: `${shipping.address_line_1 || ''} ${shipping.address_line_2 || ''}`.trim(),
      shippingCustomerName: `${shipping.first_name || 'Customer'} ${shipping.last_name || ''}`.trim(),
      shippingPhone: payment.buyer_email_address || '0000000000',
      products: [{ vid: matched.product.vid || matched.product.pid, quantity: 1 }]
    })
  });

  return res.status(200).json({ fulfilled: true, cj: await cjRes.json() });
}
