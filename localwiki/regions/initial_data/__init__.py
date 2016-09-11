# encoding=utf-8
"""
We don't use a fixture here because:

    1. Each set of pages needs to point to a different region.  Not sure how
       to do this using fixtures.
    2. Translations are easier.
"""

from django.utils.translation import ugettext as _

from pages.models import Page, slugify

NUM_DEFAULT_PAGES = 1

def populate_region(region):
    Page(
        name="Templates",
        slug="templates",
        # Translators: Please fix the links here to point to "社區," "避難收容處所", "設備物資集結點", "Restaurant" as translated in your language.  But leave the "Templates/" part of the page link.  "Templates/" in a URL is currently hard-coded and must remain in English for now.
        content=_(u"""<p>
    	Templates are special pages that serve as a starting point when creating a new page. &nbsp;Using a common template for related topics gives those pages a common structure. &nbsp;To use one of the templates, simply select the template when creating a new page. &nbsp;</p>
    <p>
    	Below is a list of the available templates. To add a new template, create a page whose title starts with &quot;Templates/&quot;, as in <a href="Templates%2FBusiness">Templates/Business</a>. &nbsp;When you create a new template, add it to this list so it&#39;s easier to find.</p>
    <h3>
    	<span>List of templates</span></h3>
    <ul>
    	<li>
    		<a href="Templates%2F社區">Templates/社區</a></li>
    	<li>
    		<a href="Templates%2F避難收容處所">Templates/避難收容處所</a></li>
    	<li>
    		<a href="Templates%2F設備物資集結點">Templates/設備物資集結點</a></li>
    	<li>
    		<a href="Templates%2F土石流保全對象">Templates/土石流保全對象</a></li>
    	<li>
    		<a href="Templates%2F水災保全對象">Templates/水災保全對象</a></li>
    	<li>
    		<a href="Templates%2F特殊需求機構">Templates/特殊需求機構</a></li>
    	<li>
    		<a href="Templates%2F重要維生設施">Templates/重要維生設施</a></li>
    	<li>
    		<a href="Templates%2F緊急聯絡網">Templates/緊急聯絡網</a></li>
    	<li>
    		<a href="Templates%2F環境不安全點">Templates/環境不安全點</a></li>
    	<li>
    		<a href="Templates%2FDisambiguation">Templates/Disambiguation</a></li>
    </ul>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/Page" - a template page
    template_type = u"社區"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""<table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>人口數</strong></td>
    		</tr>
    		<tr>
    			<td>{{人口數}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>鄰近地形</strong></td>
    		</tr>
    		<tr>
    			<td>{{鄰近地形}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>歷史災害</strong></td>
    		</tr>
    		<tr>
    			<td>{{歷史災害}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/避難收容處所" - a template page
    template_type = u"避難收容處所"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>名稱</strong></td>
    		</tr>
    		<tr>
    			<td>{{名稱}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>地址</strong></td>
    		</tr>
    		<tr>
    			<td>{{地址}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>適用災別</strong></td>
    		</tr>
    		<tr>
    			<td>{{適用災別}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>容納人數</strong></td>
    		</tr>
    		<tr>
    			<td>{{容納人數}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>面積</strong></td>
    		</tr>
    		<tr>
    			<td>{{面積}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>聯絡人</strong></td>
    		</tr>
    		<tr>
    			<td>{{聯絡人}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>電話</strong></td>
    		</tr>
    		<tr>
    			<td>{{電話}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>設備</strong></td>
    		</tr>
    		<tr>
    			<td>{{設備}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>官方／非官方</strong></td>
    		</tr>
    		<tr>
    			<td>{{官方}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/設備物資集結點" - a template page
    template_type = u"設備物資集結點"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>名稱</strong></td>
    		</tr>
    		<tr>
    			<td>{{名稱}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>地址</strong></td>
    		</tr>
    		<tr>
    			<td>{{地址}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>項目與數量</strong></td>
    		</tr>
    		<tr>
    			<td>{{項目與數量}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>聯絡人</strong></td>
    		</tr>
    		<tr>
    			<td>{{聯絡人}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>電話</strong></td>
    		</tr>
    		<tr>
    			<td>{{電話}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>官方／非官方</strong></td>
    		</tr>
    		<tr>
    			<td>{{官方}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/土石流保全對象" - a template page
    template_type = u"土石流保全對象"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>災害類型</strong></td>
    		</tr>
    		<tr>
    			<td>{{災害類型}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>人數</strong></td>
    		</tr>
    		<tr>
    			<td>{{人數}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>上傳日期</strong></td>
    		</tr>
    		<tr>
    			<td>{{上傳日期}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>官方／非官方</strong></td>
    		</tr>
    		<tr>
    			<td>{{官方}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/水災保全對象" - a template page
    template_type = u"水災保全對象"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>人數</strong></td>
    		</tr>
    		<tr>
    			<td>{{人數}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>上傳日期</strong></td>
    		</tr>
    		<tr>
    			<td>{{上傳日期}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>官方／非官方</strong></td>
    		</tr>
    		<tr>
    			<td>{{官方}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/特殊需求機構" - a template page
    template_type = u"特殊需求機構"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>名稱</strong></td>
    		</tr>
    		<tr>
    			<td>{{名稱}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>地址</strong></td>
    		</tr>
    		<tr>
    			<td>{{地址}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>聯絡人</strong></td>
    		</tr>
    		<tr>
    			<td>{{聯絡人}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>電話</strong></td>
    		</tr>
    		<tr>
    			<td>{{電話}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/重要維生設施" - a template page
    template_type = u"重要維生設施"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>名稱</strong></td>
    		</tr>
    		<tr>
    			<td>{{名稱}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>地址</strong></td>
    		</tr>
    		<tr>
    			<td>{{地址}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>座標</strong></td>
    		</tr>
    		<tr>
    			<td>{{座標}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/緊急聯絡網" - a template page
    template_type = u"緊急聯絡網"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>名稱</strong></td>
    		</tr>
    		<tr>
    			<td>{{名稱}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>電話</strong></td>
    		</tr>
    		<tr>
    			<td>{{電話}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>地址</strong></td>
    		</tr>
    		<tr>
    			<td>{{地址}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/環境不安全點" - a template page
    template_type = u"環境不安全點"
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_(u"""
    <table>
    	<tbody>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>地址或位置</strong></td>
    		</tr>
    		<tr>
    			<td>{{位置}}</td>
    		</tr>
    		<tr>
    			<td style="background-color: rgb(232, 236, 239);">
    				<strong>狀況描述</strong></td>
    		</tr>
    		<tr>
    			<td>{{狀況描述}}</td>
    		</tr>
    	</tbody>
    </table>"""),
        region=region
    ).save()

    # Translators: This is for "Templates/Disambiguation" - a template page
    template_type = _("Disambiguation")
    Page(
        name="Templates/%s" % template_type,
        slug="templates/%s" % slugify(template_type),
        content=_("""<p>
    	This has multiple meanings. You are probably looking for information on one of the following:</p>
    <ul>
    	<li>
    		<a href="ItemOne">ItemOne</a>&nbsp;- A brief summary of ItemOne</li>
    	<li>
    		<a href="ItemTwo">ItemTwo</a>&nbsp;- A brief summary of ItemTwo</li>
    </ul>
    <p>
    	&nbsp;</p>
    <p>
    	This is a&nbsp;<em>disambiguation</em> page&nbsp;&mdash; a navigational aid which lists other pages that might otherwise share the same title. If an page link referred you here, you might want to go back and fix it to point directly to the intended page.</p>"""),
        region=region
    ).save()

    frontpage = Page(
        name="Front Page",
        slug="front page",
        content=(_("""<p>
    	Welcome to the new LocalWiki region for %(region)s! There are currently just a handful of pages in it, to get you started.
    <p>
    	Click on <strong>Explore</strong> at the top to see what's here now.</p>
    <p>
    	You can edit this and any other page by clicking the <strong>Edit</strong> button.</p>
    <p>Need <strong>help</strong>? Please see the <a href="http://localwiki.net/main/Help">help page</a> on the <a href="http://localwiki.net/main/">LocalWiki Guide</a>!</p>""") % {'region': region.full_name}),
        region=region
    ).save()

    frontpage.content = _("""<p>
    Welcome to the new LocalWiki region for %(region)s!  Here are some information about this area.
    <h2>Environment</h2>
    <h2>Disaster Potential</h2>
    <h2>Historical Disasters</h2>
    """)
    frontpage.save()
